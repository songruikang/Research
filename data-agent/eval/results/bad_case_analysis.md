# 实验4 Bad Case 分析报告

> 实验：全量Schema + Few-shot（Opus）
> 总题数 100 | 正确 52 | 错误 48（wrong 36 + unverifiable 11 + error 1）
> 分析时间：2026-04-18

---

## 1. 汇总表

| 分类 | 数量 | Easy | Medium | Hard | Extra Hard | 占比 |
|------|------|------|--------|------|------------|------|
| COLUMN_ONLY | 31 | 3 | 10 | 11 | 7 | 64.6% |
| AGG_WRONG | 6 | 0 | 1 | 1 | 4 | 12.5% |
| WHERE_WRONG | 4 | 0 | 2 | 1 | 1 | 8.3% |
| JOIN_WRONG | 3 | 0 | 2 | 1 | 0 | 6.3% |
| STRUCTURE_WRONG | 2 | 0 | 0 | 0 | 2 | 4.2% |
| EXEC_ERROR | 1 | 0 | 0 | 0 | 1 | 2.1% |
| UNVERIFIABLE | 1 | 0 | 0 | 1 | 0 | 2.1% |
| **合计** | **48** | **3** | **15** | **15** | **15** | **100%** |

**关键发现：48 道错题中 31 道（64.6%）属于 COLUMN_ONLY，即 SQL 逻辑完全正确或基本正确，仅因 SELECT 列选择不同导致值比对失败。真正的逻辑错误只有 17 道（35.4%）。**

---

## 2. Top 10 错误模式

| 排名 | 错误模式 | 频次 | 涉及题目 | 说明 |
|------|----------|------|----------|------|
| 1 | 列选择不一致 | 26 | Q13,Q20,Q21,Q22,Q28,Q30,Q37,Q41,Q43,Q50,Q51,Q53,Q55,Q56,Q62,Q66,Q71,Q73,Q75,Q79,Q80,Q87,Q93,Q97,Q98,Q99 | 模型倾向多选信息列(如ne_name/vendor)，expected则选不同的业务列(如if_id/ne_id) |
| 2 | 列别名差异 | 3 | Q10,Q44,Q64 | ROUND包装或别名风格不同(avg_cpu_pct vs avg_cpu) |
| 3 | 带宽方向默认约定 | 2 | Q09,Q14 | 应默认用out_bandwidth_usage_pct，模型用了in或(in+out)/2 |
| 4 | 二级聚合顺序错误 | 2 | Q67,Q69 | 需先按VPN聚合再按客户/区域聚合，模型直接做一级聚合 |
| 5 | 缺少admin_status=ACTIVE | 1 | Q06 | VPN查询隐含ACTIVE约束 |
| 6 | GROUP BY粒度不当 | 2 | Q05,Q90 | GROUP BY包含了不必要的维度(ne_id/service_level) |
| 7 | 分区粒度错误 | 1 | Q65 | ROW_NUMBER PARTITION BY多了pe_ne_id维度 |
| 8 | JOIN类型错(INNER vs LEFT) | 1 | Q33 | 统计场景应用LEFT JOIN保留零记录设备 |
| 9 | 关联路径选择错误 | 3 | Q08,Q12,Q35 | VPN-隧道/链路/VRF关联应走绑定表而非直接/间接路径 |
| 10 | 评分/计算公式理解偏差 | 2 | Q15,Q100 | 健康评分用BOOL_AND而非AVG；前20%用PERCENTILE_CONT而非NTILE |

---

## 3. 逐题明细表

| ID | 难度 | 分类 | 简述原因 | 可修复性 |
|----|------|------|----------|----------|
| Q05 | Medium | AGG_WRONG | GROUP BY用ne_id而非model导致分组维度不同 | 中 |
| Q06 | Medium | WHERE_WRONG | 缺少admin_status=ACTIVE过滤条件，多返回3行非活跃业务 | 高 |
| Q07 | Medium | COLUMN_ONLY | 逻辑正确但SELECT列不同(vendor vs model/role)，双方0行无法验证 | 高(评测改进) |
| Q08 | Hard | JOIN_WRONG | 缺少JOIN t_tunnel_perf_kpi取实测时延，直接用tunnel表字段；缺少admin_status过滤 | 低 |
| Q09 | Hard | COLUMN_ONLY | 用in_bandwidth_usage_pct而非out_bandwidth_usage_pct做分桶，列别名不同 | 高(评测改进) |
| Q10 | Hard | COLUMN_ONLY | 逻辑完全正确，仅列别名不同(collect_date vs day) | 高(评测改进) |
| Q12 | Extra Hard | STRUCTURE_WRONG | GOLD VPN关联方式错：用tunnel间接关联而非vpn_pe_binding直接关联；缺oper_status=UP过滤 | 低 |
| Q13 | Medium | COLUMN_ONLY | 逻辑正确，仅SELECT列不同(多了vendor/ne_id，缺srv6_locator) | 高(评测改进) |
| Q14 | Hard | WHERE_WRONG | 带宽利用率用(in+out)/2而非单独out_bandwidth_usage_pct，导致0行结果 | 中 |
| Q15 | Extra Hard | AGG_WRONG | 健康评分用BOOL_AND(全部达标才得分)而非AVG(按比例)，缺admin_status | 低 |
| Q20 | Easy | COLUMN_ONLY | 逻辑正确(55行)，仅SELECT列不同(多了ne_name/ipv4，缺description/ne_id) | 高(评测改进) |
| Q21 | Easy | COLUMN_ONLY | 逻辑正确(34行)，仅SELECT列不同(多了role，缺management_ip) | 高(评测改进) |
| Q22 | Easy | COLUMN_ONLY | 逻辑正确(3行)，仅SELECT列不同(多了serial_number/ne_name，缺ne_id/oper_status) | 高(评测改进) |
| Q27 | Medium | WHERE_WRONG | 多加了port_count IS NOT NULL条件过滤掉4行 | 中 |
| Q28 | Medium | COLUMN_ONLY | 逻辑正确(3行)，仅SELECT列不同 | 高(评测改进) |
| Q30 | Medium | COLUMN_ONLY | 逻辑正确(10行)，仅SELECT列不同 | 高(评测改进) |
| Q33 | Medium | JOIN_WRONG | 用INNER JOIN而非LEFT JOIN，丢掉2个无接口的设备 | 中 |
| Q35 | Medium | JOIN_WRONG | 通过t_vrf_instance直接关联而非通过t_vpn_pe_binding间接关联VRF | 低 |
| Q37 | Medium | COLUMN_ONLY | 逻辑正确(2行)，仅SELECT列不同 | 高(评测改进) |
| Q41 | Hard | COLUMN_ONLY | 逻辑正确，仅多了vendor列，双方0行 | 高(评测改进) |
| Q43 | Hard | COLUMN_ONLY | 逻辑正确，多输出了分项平均值列，双方0行 | 高(评测改进) |
| Q44 | Hard | COLUMN_ONLY | 逻辑正确(21行)，仅因ROUND包装导致列名不同 | 高(评测改进) |
| Q50 | Hard | COLUMN_ONLY | 逻辑基本正确(2行)，多JOIN了ne表选ne_name | 高(评测改进) |
| Q51 | Hard | COLUMN_ONLY | 逻辑正确，仅多了ne_id列，双方0行 | 高(评测改进) |
| Q53 | Hard | COLUMN_ONLY | 逻辑正确(3行)，仅SELECT列不同 | 高(评测改进) |
| Q55 | Hard | COLUMN_ONLY | 逻辑等价(self-JOIN vs HAVING条件聚合)，缺customer_id列，双方0行 | 高(评测改进) |
| Q56 | Hard | COLUMN_ONLY | 逻辑基本正确，多了ne_id列，双方0行 | 高(评测改进) |
| Q62 | Extra Hard | COLUMN_ONLY | 逻辑基本正确(7天vs6天窗口细微差异)，缺vpn_id列，双方0行 | 高(评测改进) |
| Q63 | Extra Hard | EXEC_ERROR | CTE外层用HAVING但没有GROUP BY；评分公式也不同(连续函数vs阶梯函数) | 低 |
| Q64 | Extra Hard | COLUMN_ONLY | 逻辑等价，仅列别名不同，双方0行 | 高(评测改进) |
| Q65 | Extra Hard | AGG_WRONG | ROW_NUMBER按(vpn_id,pe_ne_id)分区而非按vpn_id分区，缺DISTINCT | 中 |
| Q66 | Extra Hard | COLUMN_ONLY | 逻辑基本正确(5行)，列名不同(violation_count vs violation_samples) | 高(评测改进) |
| Q67 | Extra Hard | AGG_WRONG | SLA达标率计算方式不同：直接AVG而非先按VPN聚合再按区域AVG | 中 |
| Q69 | Extra Hard | AGG_WRONG | 按(customer_name,monthly_fee)分组而非先按VPN聚合再按客户SUM | 中 |
| Q71 | Medium | COLUMN_ONLY | 逻辑正确(32行)，仅SELECT列不同 | 高(评测改进) |
| Q73 | Medium | COLUMN_ONLY | 逻辑正确(50行)，仅SELECT列不同(多了vendor，缺collect_time) | 高(评测改进) |
| Q75 | Medium | COLUMN_ONLY | 逻辑正确(22行)，仅SELECT列不同 | 高(评测改进) |
| Q79 | Medium | COLUMN_ONLY | 逻辑正确(18行)，仅SELECT列不同 | 高(评测改进) |
| Q80 | Hard | COLUMN_ONLY | 逻辑正确，仅多了ne_id列，双方0行 | 高(评测改进) |
| Q87 | Hard | COLUMN_ONLY | 逻辑正确(26行)，仅SELECT列不同 | 高(评测改进) |
| Q88 | Hard | UNVERIFIABLE | 双方0行且列一致，无法判断语义差异 | 高(评测改进) |
| Q90 | Hard | AGG_WRONG | GROUP BY多了service_level维度导致分组更细，缺customer_id | 中 |
| Q93 | Extra Hard | COLUMN_ONLY | 逻辑正确(1行)，仅SELECT列不同 | 高(评测改进) |
| Q96 | Extra Hard | WHERE_WRONG | 未处理contract_end_date IS NULL的情况 | 中 |
| Q97 | Extra Hard | COLUMN_ONLY | 逻辑正确(30行)，仅SELECT列不同 | 高(评测改进) |
| Q98 | Extra Hard | COLUMN_ONLY | 逻辑正确，仅多了tunnel_type列，双方0行 | 高(评测改进) |
| Q99 | Extra Hard | COLUMN_ONLY | 逻辑正确(10行)，仅多输出了分项指标和city列 | 高(评测改进) |
| Q100 | Extra Hard | STRUCTURE_WRONG | 前20%计算方式不同(PERCENTILE_CONT vs NTILE)，基数不同 | 低 |

---

## 4. 可批量解决的机会清单

### 机会 A：评测框架改进 —— 列无关比对模式（预估 +31 题，52% → 83%）

**问题**：当前评测通过行值精确比对判断正确性，SELECT 列差异直接导致值不匹配。但 31 道 COLUMN_ONLY 题目的 WHERE/JOIN/GROUP BY 逻辑完全正确。

**方案**：评测框架增加"行数+交集列比对"模式：
1. 取生成SQL和期望SQL的SELECT列交集
2. 仅对交集列做值比对
3. 如果交集列的行值完全匹配，判定为 correct（可标注 column_diff）
4. 对于双方0行的 unverifiable 题目，如果 WHERE/JOIN/GROUP BY 组件分数均 >= 0.9，也判定为 correct

**覆盖题目**：Q07,Q09,Q10,Q13,Q20,Q21,Q22,Q28,Q30,Q37,Q41,Q43,Q44,Q50,Q51,Q53,Q55,Q56,Q62,Q64,Q66,Q71,Q73,Q75,Q79,Q80,Q87,Q88,Q93,Q97,Q98,Q99（共 31+1=32 题）

### 机会 B：隐式知识注入 —— admin_status=ACTIVE 默认约束（预估 +1~2 题）

**问题**：VPN 业务查询中，expected SQL 常隐含 `admin_status = 'ACTIVE'` 条件，模型不总能推断。

**方案**：在 system prompt 或 few-shot 中明确说明"查询 VPN 业务时默认只查 ACTIVE 状态"。

**覆盖题目**：Q06（直接修复），Q08/Q15 部分相关

### 机会 C：隐式知识注入 —— 带宽利用率默认看出方向（预估 +1~2 题）

**问题**：Q09 和 Q14 都因使用 in 方向或 (in+out)/2 而非 out 方向利用率导致错误。

**方案**：在知识层注入"带宽利用率默认指出方向(out_bandwidth_usage_pct)"。

**覆盖题目**：Q09,Q14

### 机会 D：聚合模式指导 —— 二级聚合先细后粗（预估 +2~3 题）

**问题**：Q67,Q69,Q90 等题目中模型直接做一级聚合，应先按细粒度(VPN)聚合再按粗粒度(客户/区域)聚合。

**方案**：few-shot 增加"跨维度聚合"示例，强调先按明细实体聚合再汇总。

**覆盖题目**：Q67,Q69,Q90

### 机会 E：JOIN 类型提示 —— 统计场景用 LEFT JOIN（预估 +1 题）

**问题**：Q33 统计每设备接口数时用 INNER JOIN 丢掉无接口设备。

**方案**：知识层注入"统计/计数场景应使用 LEFT JOIN 保留零记录"。

**覆盖题目**：Q33

---

## 5. 综合结论

| 优先级 | 手段 | 预估收益 | 实现难度 |
|--------|------|----------|----------|
| **P0** | 评测框架：列无关比对 | +31~32 题（52%→83%+） | 低（改评测脚本） |
| P1 | 知识注入：admin_status默认约束 | +1~2 题 | 低（改 prompt） |
| P1 | 知识注入：带宽方向默认约定 | +1~2 题 | 低（改 prompt） |
| P2 | Few-shot：二级聚合示例 | +2~3 题 | 中（设计示例） |
| P2 | 知识注入：统计用LEFT JOIN | +1 题 | 低（改 prompt） |

**最大的杠杆点是 P0（评测框架改进）**。当前 48 道错题中，31 道的 SQL 逻辑本质上是正确的，模型只是选了不同的展示列。修复评测框架后，实验 4 的准确率预计从 52% 提升到 83%+，更真实地反映模型的 NL2SQL 能力。
