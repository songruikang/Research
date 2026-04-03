# Telecom NMS Schema Integration v1

> 日期: 2025-03-31
> 目标: 将电信网管系统(NMS)的Schema和模拟数据集成到WrenAI，作为NL2SQL二次开发和测试的基础

---

## 1. 输入文件（用户提供）

| 文件 | 路径 | 说明 |
|------|------|------|
| 字段字典CSV | `WrenAI/nms_field_dictionary_full.csv` | 14张表、356个字段的全量元数据（类型、中文描述、外键、枚举值等） |
| 完整方案MD | `WrenAI/telecom_nl2sql_complete_guide.md` | Schema文档 + 15道QA测试(Q01-Q15) + 测试策略 + 数据规模建议 |

## 2. 生成的产物

| 文件 | 大小 | 用途 |
|------|------|------|
| `telecom_mdl.json` | 125K | WrenAI MDL语义层JSON（14模型、29关系、356列含中文description） |
| `telecom_init.sql` | 4.9M | DuckDB初始化SQL（14张CREATE TABLE + 21,086行INSERT数据） |
| `telecom_nms.duckdb` | 16M | 预生成的DuckDB数据库文件（可直接查询） |
| `telecom_test_cases.json` | 10K | 15道QA测试对（问题 + 预期SQL + 隐含知识说明） |

## 3. 工具脚本（`telecom/` 包）

```
telecom/
  __init__.py
  csv_to_ddl.py          # CSV → CREATE TABLE DDL（含类型修正、约束提取、FK拓扑排序）
  csv_to_mdl.py          # CSV → WrenAI MDL JSON（模型、列描述、关系映射）
  generate_mock_data.py  # 生成模拟数据 → DuckDB（seed=42可复现）
  build_init_sql.py      # 从DuckDB导出为单个init SQL文件
```

### 重新生成命令

```bash
# 重新生成MDL
.venv/bin/python -m telecom.csv_to_mdl

# 重新生成数据库（会覆盖telecom_nms.duckdb）
rm -f telecom_nms.duckdb
.venv/bin/python -m telecom.generate_mock_data

# 重新生成init SQL（依赖telecom_nms.duckdb已存在）
.venv/bin/python -m telecom.build_init_sql
```

## 4. Schema概览

**14张表 = 10张OLTP + 4张OLAP**

```
t_site ──1:N──> t_network_element ──1:N──> t_board ──1:N──> t_interface
                      │                                         │
                      ├──1:N──> t_interface                     │
                      │              ├──N:1(A/Z端)──> t_physical_link
                      │              └──1:N──> t_vrf_instance
                      ├──1:N──> t_srv6_policy ──1:N──> t_tunnel
                      └──via t_vpn_pe_binding(M:N)──> t_l3vpn_service

KPI时序: NE→t_ne_perf_kpi, 接口→t_interface_perf_kpi, 隧道→t_tunnel_perf_kpi, VPN→t_vpn_sla_kpi
```

### 模拟数据规模（开发模式）

| 表 | 行数 | 关键特征 |
|----|------|----------|
| t_site | 25 | 5大区×5城市，含TIER1/2/3 |
| t_network_element | 50 | HUAWEI/CISCO各半，PE/P/CE/RR/ASBR，5%DOWN |
| t_board | 150 | 每NE 3块(1MPU+2LPU) |
| t_interface | 512 | 混合物理/逻辑/Trunk，含100GE重点NE |
| t_physical_link | 100 | 站间/站内，含单点故障场景 |
| t_vrf_instance | 119 | 每PE 2-3个VRF |
| t_l3vpn_service | 30 | GOLD/SILVER/BRONZE，含SRV6_TE |
| t_vpn_pe_binding | 80 | 每VPN 2-5台PE |
| t_srv6_policy | 50 | 含DOWN状态，部分PE无Policy |
| t_tunnel | 80 | SRv6 BE/TE + MPLS，associated_vpn_ids为JSON |
| 4张KPI表 | ~20K | 2天×96点/天，含异常数据(CPU>80%、SLA违规等) |

## 5. WrenAI集成方式（不改WrenAI代码）

### 步骤1: 启动WrenAI

```bash
cd WrenAI/docker
cp .env.example .env.local   # 填入 OPENAI_API_KEY
cp config.example.yaml config.yaml
docker compose --env-file .env.local up -d
```

### 步骤2: 配置DuckDB数据源

打开 http://localhost:3000 → 选择DuckDB → "Initial SQL statements" 粘贴 `telecom_init.sql` 内容

### 步骤3: 提交MDL（通过API）

```bash
curl -X POST http://localhost:5555/v1/semantics-preparations \
  -H "Content-Type: application/json" \
  -d "{\"mdl\": $(cat telecom_mdl.json | jq -Rs .), \"id\": \"telecom-nms-v1\"}"

# 检查索引状态
curl http://localhost:5555/v1/semantics-preparations/telecom-nms-v1/status
```

### 步骤4: 测试

在UI中用中文提问，如"查询所有华为厂商的PE设备"。

## 6. QA测试用例（15道，已全部验证有非空结果）

| ID | 难度 | 核心考察点 | 涉及表数 |
|----|------|-----------|---------|
| Q01 | Easy | 单表过滤（华为PE+UP） | 1 |
| Q02 | Easy | 单表GROUP BY（TIER1按大区） | 1 |
| Q03 | Easy | 单表COUNT（SRv6 DOWN） | 1 |
| Q04 | Medium | 两表JOIN（北京网元+站点） | 2 |
| Q05 | Medium | JOIN+HAVING（100GE物理口>10） | 2 |
| Q06 | Medium | 三表JOIN via桥接表（SRV6_TE VPN+PE） | 3 |
| Q07 | Medium | OLAP时间过滤+聚合（CPU>80%） | 2 |
| Q08 | Hard | 多表JOIN+软关联（GOLD VPN隧道时延超SLA） | 5 |
| Q09 | Hard | CTE+CASE WHEN分桶（带宽利用率分布） | 3 |
| Q10 | Hard | 窗口函数LAG（CPU趋势环比） | 3 |
| Q11 | Extra Hard | CTE+违规率计算（SLA TOP5客户） | 2 |
| Q12 | Extra Hard | CTE+ARRAY_AGG+业务推理（单点故障链路） | 4 |
| Q13 | Medium | NOT EXISTS反向逻辑（SRv6启用无Policy） | 2 |
| Q14 | Hard | 时间窗口对比（周环比带宽增长>20pp） | 3 |
| Q15 | Extra Hard | 综合健康评分（GOLD VPN四维SLA<75分） | 2 |

## 7. 关键技术决策

| 决策 | 原因 |
|------|------|
| DECIMAL(10.7)→DECIMAL(10,7) | CSV中用句点代替逗号，DuckDB不兼容 |
| BIGSERIAL→BIGINT | DuckDB不支持BIGSERIAL，KPI表主键手动递增 |
| MDL type简化（VARCHAR(64)→VARCHAR） | WrenAI MDL不需要长度限定符 |
| 开发规模(1/10) | 21K行足够验证所有QA，生成快、文件小 |
| seed=42固定随机种子 | 数据可复现，每次生成结果一致 |
| "troubled" GOLD VPN机制 | 前2个GOLD VPN强制高违规率，确保Q15有结果 |
| associated_vpn_ids用JSON数组 | 隧道与VPN的软关联，Q08用LIKE匹配 |

## 8. 已知限制

- 模拟数据仅覆盖2天时间窗口，Q10(7天趋势)/Q14(周环比)只有部分数据
- `telecom_init.sql` 为4.9M，WrenAI UI的"Initial SQL"文本框可能有大小限制，大规模数据建议改用CSV文件+`read_csv()`方式
- MDL通过API提交时，需要WrenAI的AI Service已完成启动（Qdrant就绪）
- 未配置WrenAI的SQL Pairs功能（可将test_cases.json中的QA对导入以提升RAG质量）

## 9. 后续可做的事

- [ ] 实际部署WrenAI Docker并端到端跑通
- [ ] 将15道QA导入WrenAI的SQL Pairs（提升检索质量）
- [ ] 扩展到完整数据规模（400K+ KPI行）测试性能
- [ ] config.yaml改用Claude模型对比GPT效果
- [ ] 基于Q01-Q15做自动化评测脚本，量化准确率
