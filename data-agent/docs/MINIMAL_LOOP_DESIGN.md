# 最小闭环设计：知识驱动的 NL2SQL 准确率提升

## 核心假设

**给了正确的领域知识，模型就能生成正确的 SQL。**

验证方式：用 Opus 直接生成 100 题的 SQL，对比：
- A 组：只给 DDL schema（当前基线，12% 准确率）
- B 组：DDL + 通用规则（~30 条）
- C 组：DDL + 通用规则 + 专项定义（按题匹配）

如果 C 组准确率到 50%+，说明假设成立，知识是关键。

---

## 知识分层

### 第一层：通用规则（Global Rules）

每次查询都注入，约 500 tokens。

```yaml
# knowledge/global_rules.yaml
rules:
  # === 枚举值规范 ===
  - "vendor 字段值全大写: HUAWEI, ZTE, CISCO, JUNIPER"
  - "role 字段取值: PE(接入), P(骨干), CE(客户侧), RR(反射器), ASBR(域边界)"
  - "oper_status 取值: UP(正常), DOWN(故障), DEGRADED(降级)"
  - "admin_status 取值: UP(启用), DOWN(停用), TESTING(测试)"
  - "'在网设备'指 oper_status='UP'，不是 admin_status"

  # === 组合条件模式 ===
  - "'XXX物理端口'需同时过滤: phy_type='XXX' AND if_type='PHYSICAL'"
  - "'XXX承载的VPN'通过 underlay_type 字段过滤，不是通过隧道表"

  # === 公式模式 ===
  - "利用率类指标 = used_xxx / NULLIF(total_xxx, 0)（防除零）"
  - "达标率 = SUM(CASE WHEN met THEN 1 END) / COUNT(*)（布尔字段聚合）"
  - "百分比字段如 cpu_usage_avg_pct 存的是 0-100，不是 0-1"

  # === DuckDB 语法 ===
  - "时间间隔: INTERVAL 24 HOUR（无引号无复数），不要写 INTERVAL '24 HOURS'"
  - "布尔字段: WHERE sla_overall_met（不要写 = 'true' 或 = 1）"

  # === JOIN 常用路径 ===
  - "VPN → PE设备: t_l3vpn_service JOIN t_vpn_pe_binding ON vpn_id JOIN t_network_element ON ne_id"
  - "设备 → 站点: t_network_element JOIN t_site ON site_id"
  - "设备 → 性能KPI: t_network_element JOIN t_ne_perf_kpi ON ne_id"
  - "接口 → 性能KPI: t_interface JOIN t_interface_perf_kpi ON if_id"
```

### 第二层：专项定义（Specific Definitions）

按问题关键词匹配注入，每条 100-200 tokens。

```yaml
# knowledge/specific_definitions.yaml
definitions:
  - trigger: ["单点故障"]
    knowledge: |
      单点故障链路 = 两个站点之间只有一条物理链路。
      实现: 用 LEAST/GREATEST 归一化站点对，GROUP BY 后 HAVING COUNT(*)=1。
      如果还要求承载特定VPN，需要通过链路两端NE关联到 vpn_pe_binding。

  - trigger: ["健康评分", "健康分"]
    knowledge: |
      设备健康评分是自定义指标，需要问题中给出评分规则。
      常见模式: 多个KPI各占N分，达标得满分，不达标得0分。
      示例: CPU<70得25分 + 内存<75得25分 + ... = 总分

  - trigger: ["BGP可用率", "BGP对等体"]
    knowledge: |
      BGP对等体可用率 = bgp_peer_up_count / bgp_peer_total_count × 100
      字段在 t_ne_perf_kpi 表中。注意 NULLIF 防止除零。

  - trigger: ["VRF路由利用率"]
    knowledge: |
      VRF路由利用率 = current_route_count / max_routes × 100
      字段在 t_vrf_instance 表中。

  - trigger: ["SLA违规率", "达标率"]
    knowledge: |
      SLA达标率 = SUM(CASE WHEN sla_overall_met THEN 1 END) * 100.0 / COUNT(*)
      单项达标: sla_latency_met, sla_jitter_met, sla_loss_met, sla_availability_met
      综合达标: sla_overall_met（全部子项达标时为TRUE）

  - trigger: ["环比", "趋势", "对比上周"]
    knowledge: |
      环比变化 = 当前值 - LAG(当前值) OVER (ORDER BY 时间)
      周对比: 用 CASE WHEN 分桶到 'THIS_WEEK'/'LAST_WEEK'，分别聚合后 JOIN

  - trigger: ["流量增长", "增长最快"]
    knowledge: |
      流量增长 = 当前时段平均值 - 上一时段平均值
      双时间窗: 分别 WHERE collect_time >= NOW() - INTERVAL X 和 < NOW() - INTERVAL X

  - trigger: ["跨区域部署"]
    knowledge: |
      判断VPN是否跨区域: VPN → vpn_pe_binding → NE → site → region
      COUNT(DISTINCT region) > 1 表示跨区域

  - trigger: ["SLA状态切换"]
    knowledge: |
      SLA状态切换 = 相邻两条记录的 sla_overall_met 值不同
      用 LAG() OVER (PARTITION BY vpn_id ORDER BY collect_time) 比较前后状态
```

---

## 最小闭环流程

### Step 1: 提取知识（自动 + 人工审核）

```
输入: eval/telecom_test_cases_100.json 的 implicit_knowledge 列
处理:
  1. 用 LLM 将 100 条 implicit_knowledge 分类为"通用规则"和"专项定义"
  2. 去重合并（多题共用同一知识的合并）
  3. 输出 global_rules.yaml + specific_definitions.yaml
审核: 人工过一遍，确认没有错误

预计产出: ~25 条通用规则 + ~30 条专项定义
```

### Step 2: 验证实验（Opus 直接跑）

```
实验 A（基线）: DDL schema only → Opus 生成 SQL → 评测
实验 B（+通用规则）: DDL + global_rules → Opus 生成 SQL → 评测
实验 C（+全量知识）: DDL + global_rules + matched specific_definitions → Opus 生成 SQL → 评测

对比三组准确率，量化每层知识的 ROI
```

### Step 3: 注入 WrenAI

```
通用规则 → WrenAI Instructions API（每次查询自动注入）
专项定义 → WrenAI SQL Pairs API（作为 few-shot 示例）
         或 Instructions 里按类别组织

注入后在 WrenAI UI 上实际提问验证
```

### Step 4: 增量改进

```
跑 100 题评测 → 找到仍然失败的题 → 分析缺什么知识 → 补充 → 重跑
每轮记录:
  - 新增了什么知识
  - 修复了哪些题
  - 是否引入回退（之前对的变错了）
  - 当前准确率
```

---

## 知识注入方式对比

| 方式 | Token 成本 | 精准度 | 实现复杂度 |
|------|-----------|--------|-----------|
| 全量注入（所有知识塞进每次 prompt）| 高（~2000 tokens）| 低（无关知识干扰）| 最低 |
| 分层注入（通用规则 always + 专项按匹配）| 中（500-800 tokens）| 高 | 中等 |
| RAG 检索（向量匹配最相关的知识）| 低（200-400 tokens）| 中 | 较高 |

**推荐: 分层注入。** 通用规则 ~500 tokens 始终注入，专项定义用关键词匹配只注入相关的 2-3 条。

---

## 预期收益

| 阶段 | 准确率 | 知识量 | Token/查询 |
|------|--------|--------|-----------|
| 当前基线 | 12% | 0 | ~4000 |
| +通用规则 | 25-30% | 25 条 | +500 |
| +专项定义 | 40-50% | +30 条 | +200（匹配的） |
| +Few-shot | 50-60% | +20 QA 对 | +300 |

---

## 执行计划

```
Day 1 上午:
  - 从 100 题 implicit_knowledge 提取知识 → global_rules.yaml + specific_definitions.yaml
  - 人工审核

Day 1 下午:
  - 跑实验 A/B/C（Opus 直接生成，不走 WrenAI）
  - 量化准确率提升

Day 2:
  - 将验证有效的知识注入 WrenAI（Instructions + SQL Pairs）
  - WrenAI 端到端验证
  - 建立增量改进脚本
```
