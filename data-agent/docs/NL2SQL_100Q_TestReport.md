# NL2SQL 100题测试报告 — Claude Opus 4.6

> 生成日期: 2026-04-07

## 一、测试概述

### 1.1 测试环境

| 项目 | 内容 |
|------|------|
| **模型** | Claude Opus 4.6 (子Agent，未看到隐性知识和期望SQL) |
| **输入** | 压缩 DDL Schema (~2500 tokens) + 问题文本 |
| **数据库** | DuckDB `telecom_nms.duckdb` (14表, 时间戳已刷新到2026-04-09) |
| **评测框架** | `eval_framework.py` — 执行生成SQL与期望SQL，按行集对比 |
| **测试用例** | 100题, 覆盖Easy/Medium/Hard/Extra Hard |

### 1.2 核心指标

| 指标 | 值 |
|------|------|
| **可执行率** | 99/100 (99%) |
| **严格准确率** | 9/100 (9%) |
| **可验证准确率** | 9/77 (12%) |
| **无法验证率** | 23/100 (23%) |

### 1.3 按难度分布

| 难度 | 总数 | 正确 | 错误 | 无法验证 | 执行失败 | 可验证准确率 |
|------|------|------|------|----------|----------|-------------|
| Easy | 13 | 3 | 7 | 3 | 0 | 30% |
| Medium | 30 | 3 | 21 | 5 | 1 | 12% |
| Hard | 34 | 1 | 25 | 8 | 0 | 4% |
| Extra Hard | 23 | 2 | 14 | 7 | 0 | 12% |

## 二、Prompt 结构

子Agent接收的Prompt结构如下（用户不可见隐性知识和期望SQL）：

```
System Prompt:
  你是一个 NL2SQL 专家。根据用户问题生成 DuckDB SQL 查询。
  数据库结构：<DDL Schema>
  只返回 SQL 语句本身，不要任何解释，不要 markdown 代码块。

User Prompt:
  <自然语言问题>
```

### DDL Schema 格式示例（压缩后约2500 tokens，共14表）

```sql
-- 站点/机房表 - 物理机房、POP点的地理位置和基础设施信息
CREATE TABLE t_site (
  site_id VARCHAR PRIMARY KEY NOT NULL,  -- 站点唯一标识
  site_name VARCHAR NOT NULL,            -- 站点名称
  site_type VARCHAR NOT NULL,            -- 站点类型。取值: DC;POP;CO;COLO;EDGE
  region VARCHAR NOT NULL,               -- 所属大区
  province VARCHAR NOT NULL,             -- 省份
  city VARCHAR NOT NULL,                 -- 城市
  tier VARCHAR NOT NULL,                 -- 站点等级。取值: TIER1;TIER2;TIER3
  status VARCHAR NOT NULL,               -- 站点状态。取值: ACTIVE;DECOMMISSIONED;PLANNED
  ...
);

-- 网元/设备表 - 路由器、交换机等网络设备信息
CREATE TABLE t_network_element (
  ne_id VARCHAR PRIMARY KEY NOT NULL,
  ne_name VARCHAR NOT NULL,
  vendor VARCHAR NOT NULL,               -- 取值: HUAWEI;CISCO;ZTE;JUNIPER
  role VARCHAR NOT NULL,                 -- 取值: PE;P;CE;RR;ASBR;ABR
  oper_status VARCHAR NOT NULL,          -- 取值: UP;DOWN;DEGRADED
  ...
);
-- ... 共14表，含 RELATIONSHIPS (FOREIGN KEYS) 注释 ...
```

**关键特征**：Schema中已包含枚举值（如`取值: UP;DOWN;DEGRADED`）和中文列注释，但**不包含**：
- 业务术语与数据库值的映射关系（如"华为"→`HUAWEI`）
- 复杂业务计算公式（如"利用率=已用/总量"）
- 隐含的过滤条件（如"当前有效"需要`admin_status='ACTIVE'`）
- 具体时间窗口的定义（如"近7天"的起止时间计算方式）

## 三、逐题详细分析

### Q01 [Easy] 查询所有华为厂商的PE设备，要求运行状态正常。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多6行, 缺少6行
**表选择**: 生成=t_network_element | 期望=t_network_element
**列选择**: 生成=ne_name, model, management_ip, loopback_ipv4 | 期望=ne_id, ne_name, model, management_ip, loopback_ipv4
**行数**: 生成=6 | 期望=6
**隐性知识**: 华为→vendor='HUAWEI'；PE设备→role='PE'；运行状态正常→oper_status='UP'
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT ne_name, model, management_ip, loopback_ipv4 FROM t_network_element WHERE vendor = 'HUAWEI' AND role = 'PE' AND oper_status = 'UP'

-- 期望SQL:
SELECT ne_id, ne_name, model, management_ip, loopback_ipv4
FROM t_network_element
WHERE vendor = 'HUAWEI' AND role = 'PE' AND oper_status = 'UP';
```

---

### Q02 [Easy] 统计每个大区有多少个TIER1级别的站点。

**判定**: ✅正确
**原因**: 完全匹配
**表选择**: 生成=t_site | 期望=t_site
**列选择**: 生成=region, tier1_site_count | 期望=region, tier1_count
**行数**: 生成=5 | 期望=5
**隐性知识**: 见题目对应字段与表关系

---

### Q03 [Easy] 当前有多少条SRv6 Policy处于DOWN状态？

**判定**: ✅正确
**原因**: 完全匹配
**表选择**: 生成=t_srv6_policy | 期望=t_srv6_policy
**列选择**: 生成=down_policy_count | 期望=down_policy_count
**行数**: 生成=1 | 期望=1
**隐性知识**: SRv6 Policy→t_srv6_policy表

---

### Q04 [Medium] 查询北京市所有网元的名称、型号和所在站点名称。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多1行, 缺少1行
**表选择**: 生成=t_network_element, t_site | 期望=t_network_element, t_site
**列选择**: 生成=ne_name, model, site_name | 期望=ne_name, model, role, site_name
**行数**: 生成=1 | 期望=1
**隐性知识**: 地理过滤在t_site上，需JOIN
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT ne.ne_name, ne.model, s.site_name FROM t_network_element ne JOIN t_site s ON ne.site_id = s.site_id WHERE s.city = '北京'

-- 期望SQL:
SELECT ne.ne_name, ne.model, ne.role, s.site_name
FROM t_network_element ne
JOIN t_site s ON ne.site_id = s.site_id
WHERE s.city = '北京';
```

---

### Q05 [Medium] 哪些设备的100GE物理端口数量超过10个？

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多2行, 缺少2行
**表选择**: 生成=t_interface, t_network_element | 期望=t_interface, t_network_element
**列选择**: 生成=ne_id, ne_name, port_100ge_count | 期望=ne_name, model, port_100ge_count
**行数**: 生成=2 | 期望=2
**隐性知识**: 100GE物理端口→phy_type='100GE' AND if_type='PHYSICAL'
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT ne.ne_id, ne.ne_name, COUNT(*) AS port_100ge_count FROM t_interface i JOIN t_network_element ne ON i.ne_id = ne.ne_id WHERE i.if_type = 'PHYSICAL' AND i.phy_type = '100GE' GROUP BY ne.ne_id, ne.ne_name HAVING COUNT(*) > 10

-- 期望SQL:
SELECT ne.ne_name, ne.model, COUNT(*) AS port_100ge_count
FROM t_network_element ne
JOIN t_interface i ON ne.ne_id = i.ne_id
WHERE i.phy_type = '100GE' AND i.if_type = 'PHYSICAL'
GROUP BY ne.ne_name, ne.model
HAVING COUNT(*) > 10
ORDER BY port_100ge_count DESC;
```

---

### Q06 [Medium] 查询使用SRv6 TE承载的所有L3VPN业务及其关联的PE设备名称。

**判定**: ⚠️错误
**原因**: 行数不同: 生成29行 vs 期望26行
**表选择**: 生成=t_l3vpn_service, t_network_element, t_vpn_pe_binding | 期望=t_l3vpn_service, t_network_element, t_vpn_pe_binding
**列选择**: 生成=vpn_id, vpn_name, customer_name, pe_name | 期望=vpn_name, customer_name, service_level, pe_name, management_ip
**行数**: 生成=29 | 期望=26
**隐性知识**: SRv6 TE承载→underlay_type='SRV6_TE'；需经过vpn_pe_binding桥接表
**知识缺口**: 返回列不同, 枚举值/条件缺失

**SQL对比**:

```sql
-- 生成SQL:
SELECT v.vpn_id, v.vpn_name, v.customer_name, ne.ne_name AS pe_name FROM t_l3vpn_service v JOIN t_vpn_pe_binding b ON v.vpn_id = b.vpn_id JOIN t_network_element ne ON b.ne_id = ne.ne_id WHERE v.underlay_type = 'SRV6_TE'

-- 期望SQL:
SELECT v.vpn_name, v.customer_name, v.service_level,
       ne.ne_name AS pe_name, ne.management_ip
FROM t_l3vpn_service v
JOIN t_vpn_pe_binding b ON v.vpn_id = b.vpn_id
JOIN t_network_element ne ON b.ne_id = ne.ne_id
WHERE v.underlay_type = 'SRV6_TE' AND v.admin_status = 'ACTIVE';
```

---

### Q07 [Medium] 查询过去24小时CPU平均利用率超过80%的网元。

**判定**: ⚠️错误
**原因**: 行数不同: 生成276行 vs 期望3行
**表选择**: 生成=t_ne_perf_kpi, t_network_element | 期望=t_ne_perf_kpi, t_network_element
**列选择**: 生成=ne_id, ne_name, cpu_usage_avg_pct, collect_time | 期望=ne_name, model, role, avg_cpu, peak_cpu
**行数**: 生成=276 | 期望=3
**隐性知识**: 时间范围理解；OLTP+OLAP JOIN
**知识缺口**: 返回列不同, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT DISTINCT ne.ne_id, ne.ne_name, k.cpu_usage_avg_pct, k.collect_time FROM t_ne_perf_kpi k JOIN t_network_element ne ON k.ne_id = ne.ne_id WHERE k.collect_time >= NOW() - INTERVAL 24 HOUR AND k.cpu_usage_avg_pct > 80

-- 期望SQL:
SELECT ne.ne_name, ne.model, ne.role,
       AVG(k.cpu_usage_avg_pct) AS avg_cpu,
       MAX(k.cpu_usage_max_pct) AS peak_cpu
FROM t_ne_perf_kpi k
JOIN t_network_element ne ON k.ne_id = ne.ne_id
WHERE k.collect_time >= NOW() - INTERVAL '24 hours'
GROUP BY ne.ne_name, ne.model, ne.role
HAVING AVG(k.cpu_usage_avg_pct) > 80
ORDER BY avg_cpu DESC;
```

---

### Q08 [Hard] 找出GOLD级别VPN业务中，隧道实测时延超过SLA要求的记录。

**判定**: ⚠️错误
**原因**: 行数不同: 生成0行 vs 期望4行
**表选择**: 生成=t_l3vpn_service, t_tunnel, t_tunnel_perf_kpi | 期望=t_l3vpn_service, t_network_element, t_tunnel, t_tunnel_perf_kpi
**列选择**: 生成=vpn_name, customer_name, sla_max_latency, measured_latency, tunnel_name, collect_time | 期望=vpn_name, sla_limit, tunnel_name, actual_latency, source, dest
**行数**: 生成=0 | 期望=4
**隐性知识**: 需关联VPN→隧道→隧道KPI；SLA阈值在t_l3vpn_service.max_latency_ms上
**知识缺口**: 返回列不同, JOIN路径错误, 枚举值/条件缺失, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT v.vpn_name, v.customer_name, v.max_latency_ms AS sla_max_latency, tk.latency_avg_ms AS measured_latency, t.tunnel_name, tk.collect_time FROM t_l3vpn_service v JOIN t_tunnel t ON v.vpn_id::VARCHAR = ANY(string_split(REPLACE(REPLACE(t.associated_vpn_ids, '[', ''), ']', ''), ',')) JOIN t_tunnel_perf_kpi tk ON t.tunnel_id = tk.tunnel_id WHERE v.service_level = 'GOLD' AND tk.latency_avg_ms > v.max_latency_ms

-- 期望SQL:
SELECT v.vpn_name, v.max_latency_ms AS sla_limit,
       t.tunnel_name, tp.latency_avg_ms AS actual_latency,
       ne_s.ne_name AS source, ne_d.ne_name AS dest
FROM t_l3vpn_service v
JOIN t_tunnel t ON t.associated_vpn_ids LIKE CONCAT('%', v.vpn_id, '%')
JOIN t_tunnel_perf_kpi tp ON t.tunnel_id = tp.tunnel_id
JOIN t_network_element ne_s ON t.source_ne_id = ne_s.ne_id
JOIN t_network_element ne_d ON t.dest_ne_id = ne_d.ne_id
WHERE v.service_level = 'GOLD' AND v.admin_status = 'ACTIVE'
  AND tp.co...
```

---

### Q09 [Hard] 统计每台PE设备上所有物理接口的带宽利用率分布（空闲<30%/正常30-70%/繁忙70-90%/过载>90%），只看最新一个采集周期。

**判定**: ✅正确
**原因**: 完全匹配
**表选择**: 生成=t_interface, t_interface_perf_kpi, t_network_element | 期望=t_interface, t_interface_perf_kpi, t_network_element
**列选择**: 生成=ne_name, idle_count, normal_count, busy_count, overload_count | 期望=ne_name, idle, normal, busy, overload
**行数**: 生成=18 | 期望=18
**隐性知识**: 见题目对应字段与表关系

---

### Q10 [Hard] 查看过去7天华北区域PE设备的每日平均CPU利用率趋势及环比变化。

**判定**: ⚠️错误
**原因**: 行数不同: 生成9行 vs 期望3行
**表选择**: 生成=t_ne_perf_kpi, t_network_element, t_site | 期望=t_ne_perf_kpi, t_network_element, t_site
**列选择**: 生成=ne_name, dt, avg_cpu, day_over_day_change | 期望=day, avg_cpu, change
**行数**: 生成=9 | 期望=3
**隐性知识**: 华北区域→region='华北'
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
WITH daily_avg AS (SELECT ne.ne_id, ne.ne_name, CAST(k.collect_time AS DATE) AS dt, AVG(k.cpu_usage_avg_pct) AS avg_cpu FROM t_ne_perf_kpi k JOIN t_network_element ne ON k.ne_id = ne.ne_id JOIN t_site s ON ne.site_id = s.site_id WHERE s.region = '华北' AND ne.role = 'PE' AND k.collect_time >= NOW() - INTERVAL 7 DAY GROUP BY ne.ne_id, ne.ne_name, CAST(k.collect_time AS DATE)) SELECT d.ne_name, d.dt, d.avg_cpu, d.avg_cpu - LAG(d.avg_cpu) OVER (PARTITION BY d.ne_id ORDER BY d.dt) AS day_over_day_chan...

-- 期望SQL:
WITH daily AS (
  SELECT DATE(k.collect_time) AS day, AVG(k.cpu_usage_avg_pct) AS avg_cpu
  FROM t_ne_perf_kpi k
  JOIN t_network_element ne ON k.ne_id = ne.ne_id
  JOIN t_site s ON ne.site_id = s.site_id
  WHERE s.region = '华北' AND ne.role = 'PE'
    AND k.collect_time >= CURRENT_DATE - INTERVAL '7 days'
  GROUP BY DATE(k.collect_time)
)
SELECT day, ROUND(avg_cpu, 2) AS avg_cpu,
       ROUND(avg_cpu - LAG(avg_cpu) OVER (ORDER BY day), 2) AS change
FROM daily ORDER BY day;
```

---

### Q11 [Extra Hard] 找出SLA违规率最高的前5个VPN客户，统计每个客户的VPN数量、总违规次数和违规率（最近30天）。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多5行, 缺少5行
**表选择**: 生成=t_l3vpn_service, t_vpn_sla_kpi | 期望=t_l3vpn_service, t_vpn_sla_kpi
**列选择**: 生成=customer_id, customer_name, vpn_count, violation_count, violation_rate_pct | 期望=customer_name, vpn_count, violations, total_samples, violation_rate_pct
**行数**: 生成=5 | 期望=5
**隐性知识**: 见题目对应字段与表关系
**知识缺口**: 返回列不同, 枚举值/条件缺失

**SQL对比**:

```sql
-- 生成SQL:
WITH violation_stats AS (SELECT v.customer_id, v.customer_name, COUNT(DISTINCT v.vpn_id) AS vpn_count, COUNT(*) AS total_records, SUM(CASE WHEN NOT sk.sla_overall_met THEN 1 ELSE 0 END) AS violation_count FROM t_l3vpn_service v JOIN t_vpn_sla_kpi sk ON v.vpn_id = sk.vpn_id WHERE sk.collect_time >= NOW() - INTERVAL 30 DAY GROUP BY v.customer_id, v.customer_name) SELECT customer_id, customer_name, vpn_count, violation_count, ROUND(violation_count * 100.0 / total_records, 2) AS violation_rate_pct F...

-- 期望SQL:
WITH stats AS (
  SELECT v.customer_id, v.customer_name,
    COUNT(DISTINCT v.vpn_id) AS vpn_count,
    COUNT(sk.kpi_id) AS total_samples,
    SUM(CASE WHEN sk.sla_overall_met = FALSE THEN 1 ELSE 0 END) AS violations
  FROM t_l3vpn_service v
  JOIN t_vpn_sla_kpi sk ON v.vpn_id = sk.vpn_id
  WHERE sk.collect_time >= CURRENT_DATE - INTERVAL '30 days'
    AND v.admin_status = 'ACTIVE'
  GROUP BY v.customer_id, v.customer_name
)
SELECT customer_name, vpn_count, violations, total_samples,
  ROUND(vio...
```

---

### Q12 [Extra Hard] 找出所有'单点故障'链路——两个站点之间只有一条物理链路、且该链路承载了GOLD级别VPN业务。

**判定**: ⚠️错误
**原因**: 行数不同: 生成9行 vs 期望22行
**表选择**: 生成=t_interface, t_l3vpn_service, t_physical_link, t_site, t_vpn_pe_binding | 期望=t_l3vpn_service, t_physical_link, t_site, t_vpn_pe_binding
**列选择**: 生成=a_site_id, a_site_name, z_site_id, z_site_name, link_name | 期望=link_name, site_a, site_b, bandwidth_mbps, distance_km
**行数**: 生成=9 | 期望=22
**隐性知识**: 单点故障需推断为站点间链路数=1；链路→NE→VPN的间接关联
**知识缺口**: 返回列不同, JOIN路径错误, 枚举值/条件缺失, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
WITH single_links AS (SELECT a_site_id, z_site_id, MIN(link_id) AS link_id FROM t_physical_link GROUP BY a_site_id, z_site_id HAVING COUNT(*) = 1) SELECT sl.a_site_id, sa.site_name AS a_site_name, sl.z_site_id, sz.site_name AS z_site_name, pl.link_name FROM single_links sl JOIN t_physical_link pl ON pl.link_id = sl.link_id JOIN t_site sa ON sl.a_site_id = sa.site_id JOIN t_site sz ON sl.z_site_id = sz.site_id WHERE EXISTS (SELECT 1 FROM t_vpn_pe_binding b JOIN t_l3vpn_service v ON b.vpn_id = v.v...

-- 期望SQL:
WITH site_pair AS (
  SELECT LEAST(a_site_id, z_site_id) AS s1,
         GREATEST(a_site_id, z_site_id) AS s2,
         COUNT(*) AS link_cnt, ARRAY_AGG(link_id) AS links
  FROM t_physical_link WHERE oper_status = 'UP'
  GROUP BY LEAST(a_site_id, z_site_id), GREATEST(a_site_id, z_site_id)
  HAVING COUNT(*) = 1
),
gold_links AS (
  SELECT DISTINCT pl.link_id
  FROM t_physical_link pl
  JOIN t_vpn_pe_binding b ON b.ne_id = pl.a_ne_id
  JOIN t_l3vpn_service v ON b.vpn_id = v.vpn_id
  WHERE v.service...
```

---

### Q13 [Medium] 哪些PE已经使能了SRv6但还没有创建任何SRv6 Policy？

**判定**: ⚠️错误
**原因**: 行数不同: 生成0行 vs 期望6行
**表选择**: 生成=t_network_element, t_srv6_policy | 期望=t_network_element, t_srv6_policy
**列选择**: 生成=ne_id, ne_name | 期望=ne_name, model, srv6_locator
**行数**: 生成=0 | 期望=6
**隐性知识**: 见题目对应字段与表关系
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT ne.ne_id, ne.ne_name FROM t_network_element ne WHERE ne.role = 'PE' AND ne.srv6_enabled AND NOT EXISTS (SELECT 1 FROM t_srv6_policy p WHERE p.source_ne_id = ne.ne_id OR p.dest_ne_id = ne.ne_id)

-- 期望SQL:
SELECT ne.ne_name, ne.model, ne.srv6_locator
FROM t_network_element ne
WHERE ne.srv6_enabled = TRUE AND ne.role = 'PE'
  AND NOT EXISTS (SELECT 1 FROM t_srv6_policy sp WHERE sp.source_ne_id = ne.ne_id);
```

---

### Q14 [Hard] 对比上周和本周各站点平均接口带宽利用率，找出增长超过20个百分点的站点。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_interface_perf_kpi, t_network_element, t_site | 期望=t_interface_perf_kpi, t_network_element, t_site
**列选择**: 生成=site_name, this_week_avg, last_week_avg, increase_pct | 期望=site_name, last_week, this_week, increase
**行数**: 生成=0 | 期望=0
**隐性知识**: 见题目对应字段与表关系
**知识缺口**: 返回列不同, 枚举值/条件缺失, 时间窗口处理

**SQL对比**:

```sql
-- 生成SQL:
WITH weekly AS (SELECT ne.site_id, CASE WHEN k.collect_time >= NOW() - INTERVAL 7 DAY THEN 'this_week' ELSE 'last_week' END AS week_label, AVG(GREATEST(k.in_bandwidth_usage_pct, k.out_bandwidth_usage_pct)) AS avg_bw FROM t_interface_perf_kpi k JOIN t_network_element ne ON k.ne_id = ne.ne_id WHERE k.collect_time >= NOW() - INTERVAL 14 DAY GROUP BY ne.site_id, week_label) SELECT s.site_name, tw.avg_bw AS this_week_avg, lw.avg_bw AS last_week_avg, ROUND(tw.avg_bw - lw.avg_bw, 2) AS increase_pct FRO...

-- 期望SQL:
WITH weekly AS (
  SELECT s.site_id, s.site_name,
    CASE WHEN k.collect_time >= CURRENT_DATE - 7 THEN 'THIS' ELSE 'LAST' END AS wk,
    AVG(k.out_bandwidth_usage_pct) AS avg_bw
  FROM t_interface_perf_kpi k
  JOIN t_network_element ne ON k.ne_id = ne.ne_id
  JOIN t_site s ON ne.site_id = s.site_id
  WHERE k.collect_time >= CURRENT_DATE - 14
  GROUP BY s.site_id, s.site_name,
    CASE WHEN k.collect_time >= CURRENT_DATE - 7 THEN 'THIS' ELSE 'LAST' END
)
SELECT tw.site_name,
  ROUND(lw.avg_bw, 2...
```

---

### Q15 [Extra Hard] 为每条GOLD级VPN业务计算健康评分（时延达标+25分，抖动达标+25分，丢包达标+25分，可用率达标+25分），输出评分低于75分的业务。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多2行, 缺少2行
**表选择**: 生成=t_l3vpn_service, t_vpn_sla_kpi | 期望=t_l3vpn_service, t_vpn_sla_kpi
**列选择**: 生成=vpn_id, vpn_name, customer_name, health_score | 期望=vpn_name, customer_name, health_score, avg_latency_ms, avg_loss_pct, availability_pct
**行数**: 生成=2 | 期望=2
**隐性知识**: 见题目对应字段与表关系
**知识缺口**: 返回列不同, 枚举值/条件缺失, 时间窗口处理

**SQL对比**:

```sql
-- 生成SQL:
WITH scores AS (SELECT v.vpn_id, v.vpn_name, v.customer_name, AVG(CASE WHEN sk.sla_latency_met THEN 25 ELSE 0 END + CASE WHEN sk.sla_jitter_met THEN 25 ELSE 0 END + CASE WHEN sk.sla_loss_met THEN 25 ELSE 0 END + CASE WHEN sk.sla_availability_met THEN 25 ELSE 0 END) AS health_score FROM t_l3vpn_service v JOIN t_vpn_sla_kpi sk ON v.vpn_id = sk.vpn_id WHERE v.service_level = 'GOLD' GROUP BY v.vpn_id, v.vpn_name, v.customer_name) SELECT vpn_id, vpn_name, customer_name, ROUND(health_score, 2) AS heal...

-- 期望SQL:
WITH health AS (
  SELECT v.vpn_id, v.vpn_name, v.customer_name,
    AVG(CASE WHEN sk.sla_latency_met THEN 25 ELSE 0 END) +
    AVG(CASE WHEN sk.sla_jitter_met THEN 25 ELSE 0 END) +
    AVG(CASE WHEN sk.sla_loss_met THEN 25 ELSE 0 END) +
    AVG(CASE WHEN sk.sla_availability_met THEN 25 ELSE 0 END) AS score,
    AVG(sk.e2e_latency_avg_ms) AS lat, AVG(sk.e2e_packet_loss_pct) AS loss,
    AVG(sk.availability_pct) AS avail
  FROM t_l3vpn_service v
  JOIN t_vpn_sla_kpi sk ON v.vpn_id = sk.vpn_id
  W...
```

---

### Q16 [Easy] 查询所有处于ACTIVE状态且合同将在90天内到期的站点。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_site | 期望=t_site
**列选择**: 生成=site_id, site_name, site_code, contract_expire_date | 期望=site_id, site_name, region, city, contract_expire_date
**行数**: 生成=0 | 期望=0
**隐性知识**: 90天内到期→contract_expire_date 在当前日期到未来90天之间；ACTIVE状态看 t_site.status
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT site_id, site_name, site_code, contract_expire_date FROM t_site WHERE status = 'ACTIVE' AND contract_expire_date <= CURRENT_DATE + INTERVAL 90 DAY AND contract_expire_date >= CURRENT_DATE

-- 期望SQL:
SELECT site_id, site_name, region, city, contract_expire_date
FROM t_site
WHERE status = 'ACTIVE'
  AND contract_expire_date IS NOT NULL
  AND contract_expire_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '90 days'
ORDER BY contract_expire_date;
```

---

### Q17 [Easy] 统计各厂商在网PE设备数量。

**判定**: ⚠️错误
**原因**: 值不同: 2行匹配, 生成多2行, 缺少2行
**表选择**: 生成=t_network_element | 期望=t_network_element
**列选择**: 生成=vendor, pe_count | 期望=vendor, pe_count
**行数**: 生成=4 | 期望=4
**隐性知识**: 在网PE设备→role=PE 且 oper_status=UP；按vendor聚合
**知识缺口**: 枚举值/条件缺失

**SQL对比**:

```sql
-- 生成SQL:
SELECT vendor, COUNT(*) AS pe_count FROM t_network_element WHERE role = 'PE' GROUP BY vendor ORDER BY pe_count DESC

-- 期望SQL:
SELECT vendor, COUNT(*) AS pe_count
FROM t_network_element
WHERE role = 'PE' AND oper_status = 'UP'
GROUP BY vendor
ORDER BY pe_count DESC, vendor;
```

---

### Q18 [Easy] 查询所有管理状态DOWN但运行状态UP的网元。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_network_element | 期望=t_network_element
**列选择**: 生成=ne_id, ne_name, management_ip, admin_status, oper_status | 期望=ne_id, ne_name, vendor, role, admin_status, oper_status
**行数**: 生成=0 | 期望=0
**隐性知识**: admin_status 和 oper_status 不是同一概念：前者是人工配置，后者是系统检测
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT ne_id, ne_name, management_ip, admin_status, oper_status FROM t_network_element WHERE admin_status = 'DOWN' AND oper_status = 'UP'

-- 期望SQL:
SELECT ne_id, ne_name, vendor, role, admin_status, oper_status
FROM t_network_element
WHERE admin_status = 'DOWN' AND oper_status = 'UP'
ORDER BY ne_name;
```

---

### Q19 [Easy] 列出所有Loopback接口及其所属设备。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多57行, 缺少57行
**表选择**: 生成=t_interface, t_network_element | 期望=t_interface, t_network_element
**列选择**: 生成=if_id, if_name, ipv4_address, ne_name | 期望=if_id, if_name, ipv4_address, ipv6_address, ne_name
**行数**: 生成=57 | 期望=57
**隐性知识**: Loopback接口→t_interface.if_type=LOOPBACK；设备名称要关联 t_network_element
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT i.if_id, i.if_name, i.ipv4_address, ne.ne_name FROM t_interface i JOIN t_network_element ne ON i.ne_id = ne.ne_id WHERE i.if_type = 'LOOPBACK'

-- 期望SQL:
SELECT i.if_id, i.if_name, i.ipv4_address, i.ipv6_address, ne.ne_name
FROM t_interface i
JOIN t_network_element ne ON i.ne_id = ne.ne_id
WHERE i.if_type = 'LOOPBACK'
ORDER BY ne.ne_name, i.if_name;
```

---

### Q20 [Easy] 查询所有400GE物理接口且运行状态为UP的端口。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多55行, 缺少55行
**表选择**: 生成=t_interface, t_network_element | 期望=t_interface
**列选择**: 生成=if_id, if_name, ne_name | 期望=if_id, if_name, ne_id, speed_mbps, description
**行数**: 生成=55 | 期望=55
**隐性知识**: 400GE物理接口→phy_type=400GE 且 if_type=PHYSICAL；端口运行状态看接口表 oper_status
**知识缺口**: 返回列不同, JOIN路径错误

**SQL对比**:

```sql
-- 生成SQL:
SELECT i.if_id, i.if_name, ne.ne_name FROM t_interface i JOIN t_network_element ne ON i.ne_id = ne.ne_id WHERE i.if_type = 'PHYSICAL' AND i.phy_type = '400GE' AND i.oper_status = 'UP'

-- 期望SQL:
SELECT if_id, if_name, ne_id, speed_mbps, description
FROM t_interface
WHERE if_type = 'PHYSICAL' AND phy_type = '400GE' AND oper_status = 'UP'
ORDER BY ne_id, if_name;
```

---

### Q21 [Easy] 查询所有已启用NETCONF和Telemetry的设备。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多34行, 缺少34行
**表选择**: 生成=t_network_element | 期望=t_network_element
**列选择**: 生成=ne_id, ne_name, management_ip | 期望=ne_id, ne_name, vendor, model, management_ip
**行数**: 生成=34 | 期望=34
**隐性知识**: 自动化友好设备→netconf_enabled=TRUE 且 telemetry_enabled=TRUE
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT ne_id, ne_name, management_ip FROM t_network_element WHERE netconf_enabled AND telemetry_enabled

-- 期望SQL:
SELECT ne_id, ne_name, vendor, model, management_ip
FROM t_network_element
WHERE netconf_enabled = TRUE AND telemetry_enabled = TRUE
ORDER BY vendor, ne_name;
```

---

### Q22 [Easy] 查询所有板卡类型为MPU且运行状态FAULT的单板。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多3行, 缺少3行
**表选择**: 生成=t_board, t_network_element | 期望=t_board
**列选择**: 生成=board_id, board_name, slot_number, ne_name | 期望=board_id, ne_id, slot_number, board_name, oper_status
**行数**: 生成=3 | 期望=3
**隐性知识**: MPU→主控板；故障单板看 t_board.oper_status=FAULT
**知识缺口**: 返回列不同, JOIN路径错误

**SQL对比**:

```sql
-- 生成SQL:
SELECT b.board_id, b.board_name, b.slot_number, ne.ne_name FROM t_board b JOIN t_network_element ne ON b.ne_id = ne.ne_id WHERE b.board_type = 'MPU' AND b.oper_status = 'FAULT'

-- 期望SQL:
SELECT b.board_id, b.ne_id, b.slot_number, b.board_name, b.oper_status
FROM t_board b
WHERE b.board_type = 'MPU' AND b.oper_status = 'FAULT'
ORDER BY b.ne_id, b.slot_number;
```

---

### Q23 [Easy] 统计每种接口类型的数量。

**判定**: ✅正确
**原因**: 完全匹配
**表选择**: 生成=t_interface | 期望=t_interface
**列选择**: 生成=if_type, if_count | 期望=if_type, if_count
**行数**: 生成=5 | 期望=5
**隐性知识**: 接口类型是逻辑类型 if_type，不是物理速率 phy_type

---

### Q24 [Easy] 查询所有未启用MPLS但角色为P的设备。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_network_element | 期望=t_network_element
**列选择**: 生成=ne_id, ne_name, management_ip | 期望=ne_id, ne_name, vendor, model, mpls_enabled
**行数**: 生成=0 | 期望=0
**隐性知识**: P设备通常应参与骨干转发；题目显式检查 mpls_enabled=FALSE 且 role=P
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT ne_id, ne_name, management_ip FROM t_network_element WHERE NOT mpls_enabled AND role = 'P'

-- 期望SQL:
SELECT ne_id, ne_name, vendor, model, mpls_enabled
FROM t_network_element
WHERE role = 'P' AND COALESCE(mpls_enabled, FALSE) = FALSE
ORDER BY ne_name;
```

---

### Q25 [Easy] 查询所有服务等级为PLATINUM且已启用加密的VPN业务。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多3行, 缺少3行
**表选择**: 生成=t_l3vpn_service | 期望=t_l3vpn_service
**列选择**: 生成=vpn_id, vpn_name, customer_name | 期望=vpn_id, vpn_name, customer_name, bandwidth_mbps, underlay_type
**行数**: 生成=3 | 期望=3
**隐性知识**: 加密VPN→encryption_enabled=TRUE；PLATINUM 是 service_level 的枚举值
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT vpn_id, vpn_name, customer_name FROM t_l3vpn_service WHERE service_level = 'PLATINUM' AND encryption_enabled

-- 期望SQL:
SELECT vpn_id, vpn_name, customer_name, bandwidth_mbps, underlay_type
FROM t_l3vpn_service
WHERE service_level = 'PLATINUM' AND encryption_enabled = TRUE
ORDER BY customer_name, vpn_name;
```

---

### Q26 [Medium] 查询每个城市当前在网PE设备数量。

**判定**: ✅正确
**原因**: 完全匹配
**表选择**: 生成=t_network_element, t_site | 期望=t_network_element, t_site
**列选择**: 生成=city, pe_count | 期望=city, pe_count
**行数**: 生成=14 | 期望=14
**隐性知识**: 在网PE设备→role=PE 且 oper_status=UP；城市来自站点表

---

### Q27 [Medium] 找出每个设备上端口数量最多的单板。

**判定**: ⚠️错误
**原因**: 行数不同: 生成61行 vs 期望50行
**表选择**: 生成=t_board | 期望=t_board, t_network_element
**列选择**: 生成=ne_id, board_id, board_name, slot_number, port_count | 期望=ne_name, board_id, slot_number, board_name, port_count
**行数**: 生成=61 | 期望=50
**隐性知识**: 每台设备内取 t_board.port_count 最大的板卡
**知识缺口**: 返回列不同, JOIN路径错误, 枚举值/条件缺失, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT b.ne_id, b.board_id, b.board_name, b.slot_number, b.port_count FROM t_board b INNER JOIN (SELECT ne_id, MAX(port_count) AS max_port_count FROM t_board GROUP BY ne_id) m ON b.ne_id = m.ne_id AND b.port_count = m.max_port_count

-- 期望SQL:
WITH ranked AS (
  SELECT b.ne_id, b.board_id, b.slot_number, b.board_name, b.port_count,
         ROW_NUMBER() OVER (PARTITION BY b.ne_id ORDER BY b.port_count DESC NULLS LAST, b.board_id) AS rn
  FROM t_board b
)
SELECT ne.ne_name, r.board_id, r.slot_number, r.board_name, r.port_count
FROM ranked r
JOIN t_network_element ne ON r.ne_id = ne.ne_id
WHERE r.rn = 1
ORDER BY ne.ne_name;
```

---

### Q28 [Medium] 查询所有站内链路中带宽大于等于100000 Mbps的链路。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多3行, 缺少3行
**表选择**: 生成=t_physical_link | 期望=t_physical_link
**列选择**: 生成=link_id, link_name, link_type, bandwidth_mbps, oper_status | 期望=link_id, link_name, a_site_id, z_site_id, bandwidth_mbps, link_type
**行数**: 生成=3 | 期望=3
**隐性知识**: 站内链路→is_intra_site=TRUE；100000 Mbps 对应 100GE 量级容量
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT pl.link_id, pl.link_name, pl.link_type, pl.bandwidth_mbps, pl.oper_status FROM t_physical_link pl WHERE pl.is_intra_site AND pl.bandwidth_mbps >= 100000

-- 期望SQL:
SELECT link_id, link_name, a_site_id, z_site_id, bandwidth_mbps, link_type
FROM t_physical_link
WHERE is_intra_site = TRUE AND bandwidth_mbps >= 100000
ORDER BY bandwidth_mbps DESC, link_id;
```

---

### Q29 [Medium] 统计每个VPN客户绑定了多少台不同的PE设备。

**判定**: ❌执行失败
**原因**: 生成SQL执行失败: Binder Error: Table "vpb" does not have a column named "customer_name"

Candidate bindings: : "site_name"

LINE 1: ... vpb JOIN t_l3vpn_service v ON vpb.vpn_id = v.vpn_id GROUP BY vpb.customer_name
                                                                         ^
**表选择**: 生成=t_l3vpn_service, t_vpn_pe_binding | 期望=t_l3vpn_service, t_vpn_pe_binding
**列选择**: 生成=无 | 期望=customer_id, customer_name, pe_device_count
**行数**: 生成=-1 | 期望=22
**隐性知识**: PE数量不能只看 pe_count 字段，应通过绑定表对 ne_id 去重统计
**知识缺口**: SQL方言问题

**SQL对比**:

```sql
-- 生成SQL:
SELECT vpb.customer_name, COUNT(DISTINCT vpb.ne_id) AS pe_count FROM t_vpn_pe_binding vpb JOIN t_l3vpn_service v ON vpb.vpn_id = v.vpn_id GROUP BY vpb.customer_name

-- 期望SQL:
SELECT v.customer_id, v.customer_name, COUNT(DISTINCT b.ne_id) AS pe_device_count
FROM t_l3vpn_service v
JOIN t_vpn_pe_binding b ON v.vpn_id = b.vpn_id
GROUP BY v.customer_id, v.customer_name
ORDER BY pe_device_count DESC, v.customer_name;
```

---

### Q30 [Medium] 查询使用EBGP接入且接入带宽大于1000 Mbps的VPN接入绑定。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多10行, 缺少10行
**表选择**: 生成=t_vpn_pe_binding | 期望=t_l3vpn_service, t_network_element, t_vpn_pe_binding
**列选择**: 生成=binding_id, vpn_id, ne_id, if_id, routing_protocol, access_bandwidth_mbps, encapsulation, site_name, oper_status | 期望=binding_id, vpn_name, ne_name, if_id, access_bandwidth_mbps, ce_as_number
**行数**: 生成=10 | 期望=10
**隐性知识**: EBGP接入看 binding.routing_protocol；接入带宽在 access_bandwidth_mbps
**知识缺口**: 返回列不同, JOIN路径错误

**SQL对比**:

```sql
-- 生成SQL:
SELECT vpb.binding_id, vpb.vpn_id, vpb.ne_id, vpb.if_id, vpb.routing_protocol, vpb.access_bandwidth_mbps, vpb.encapsulation, vpb.site_name, vpb.oper_status FROM t_vpn_pe_binding vpb WHERE vpb.routing_protocol = 'EBGP' AND vpb.access_bandwidth_mbps > 1000

-- 期望SQL:
SELECT b.binding_id, v.vpn_name, ne.ne_name, b.if_id, b.access_bandwidth_mbps, b.ce_as_number
FROM t_vpn_pe_binding b
JOIN t_l3vpn_service v ON b.vpn_id = v.vpn_id
JOIN t_network_element ne ON b.ne_id = ne.ne_id
WHERE b.routing_protocol = 'EBGP' AND b.access_bandwidth_mbps > 1000
ORDER BY b.access_bandwidth_mbps DESC, b.binding_id;
```

---

### Q31 [Medium] 找出配置了SRv6 Locator但SRv6未启用的设备。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_network_element | 期望=t_network_element
**列选择**: 生成=ne_id, ne_name, srv6_locator, srv6_enabled | 期望=ne_id, ne_name, vendor, srv6_locator, srv6_enabled
**行数**: 生成=0 | 期望=0
**隐性知识**: 配置存在不代表功能启用；需同时检查 srv6_locator 非空 且 srv6_enabled=FALSE
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT ne.ne_id, ne.ne_name, ne.srv6_locator, ne.srv6_enabled FROM t_network_element ne WHERE ne.srv6_locator IS NOT NULL AND ne.srv6_locator != '' AND NOT ne.srv6_enabled

-- 期望SQL:
SELECT ne_id, ne_name, vendor, srv6_locator, srv6_enabled
FROM t_network_element
WHERE srv6_locator IS NOT NULL AND COALESCE(srv6_enabled, FALSE) = FALSE
ORDER BY ne_name;
```

---

### Q32 [Medium] 查询所有使用MPLS_TE承载且当前运行状态为UP的VPN业务。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多6行, 缺少6行
**表选择**: 生成=t_l3vpn_service | 期望=t_l3vpn_service
**列选择**: 生成=vpn_id, vpn_name, customer_name, underlay_type, oper_status | 期望=vpn_id, vpn_name, customer_name, service_level, bandwidth_mbps
**行数**: 生成=6 | 期望=6
**隐性知识**: 承载技术取自 underlay_type；业务运行状态取 oper_status
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT v.vpn_id, v.vpn_name, v.customer_name, v.underlay_type, v.oper_status FROM t_l3vpn_service v WHERE v.underlay_type = 'MPLS_TE' AND v.oper_status = 'UP'

-- 期望SQL:
SELECT vpn_id, vpn_name, customer_name, service_level, bandwidth_mbps
FROM t_l3vpn_service
WHERE underlay_type = 'MPLS_TE' AND oper_status = 'UP'
ORDER BY customer_name, vpn_name;
```

---

### Q33 [Medium] 统计每台设备的物理接口数和Loopback接口数。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多50行, 缺少50行
**表选择**: 生成=t_interface | 期望=t_interface, t_network_element
**列选择**: 生成=ne_id, physical_if_count, loopback_if_count | 期望=ne_name, physical_if_count, loopback_if_count
**行数**: 生成=50 | 期望=50
**隐性知识**: 接口统计按逻辑类型分桶：PHYSICAL 与 LOOPBACK
**知识缺口**: 返回列不同, JOIN路径错误

**SQL对比**:

```sql
-- 生成SQL:
SELECT i.ne_id, COUNT(CASE WHEN i.if_type = 'PHYSICAL' THEN 1 END) AS physical_if_count, COUNT(CASE WHEN i.if_type = 'LOOPBACK' THEN 1 END) AS loopback_if_count FROM t_interface i GROUP BY i.ne_id

-- 期望SQL:
SELECT ne.ne_name,
       COUNT(CASE WHEN i.if_type = 'PHYSICAL' THEN 1 END) AS physical_if_count,
       COUNT(CASE WHEN i.if_type = 'LOOPBACK' THEN 1 END) AS loopback_if_count
FROM t_network_element ne
LEFT JOIN t_interface i ON ne.ne_id = i.ne_id
GROUP BY ne.ne_name
ORDER BY ne.ne_name;
```

---

### Q34 [Medium] 查询所有合同已过期但仍处于ACTIVE状态的VPN业务。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列一致)
**表选择**: 生成=t_l3vpn_service | 期望=t_l3vpn_service
**列选择**: 生成=vpn_id, vpn_name, customer_name, contract_end_date, admin_status | 期望=vpn_id, vpn_name, customer_name, contract_end_date, admin_status
**行数**: 生成=0 | 期望=0
**隐性知识**: 合同已过期→contract_end_date < CURRENT_DATE；业务仍在服务中看 admin_status=ACTIVE
**知识缺口**: 业务规则缺失

**SQL对比**:

```sql
-- 生成SQL:
SELECT v.vpn_id, v.vpn_name, v.customer_name, v.contract_end_date, v.admin_status FROM t_l3vpn_service v WHERE v.contract_end_date < CURRENT_DATE AND v.admin_status = 'ACTIVE'

-- 期望SQL:
SELECT vpn_id, vpn_name, customer_name, contract_end_date, admin_status
FROM t_l3vpn_service
WHERE admin_status = 'ACTIVE'
  AND contract_end_date IS NOT NULL
  AND contract_end_date < CURRENT_DATE
ORDER BY contract_end_date;
```

---

### Q35 [Medium] 查看每个PE设备上绑定的VRF实例数量。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多20行, 缺少20行
**表选择**: 生成=t_vpn_pe_binding | 期望=t_network_element, t_vpn_pe_binding
**列选择**: 生成=ne_id, vrf_count | 期望=ne_name, vrf_count
**行数**: 生成=20 | 期望=20
**隐性知识**: PE上的VRF通过绑定表与VRF表关联，避免直接依赖设备表字段
**知识缺口**: 返回列不同, JOIN路径错误, 枚举值/条件缺失

**SQL对比**:

```sql
-- 生成SQL:
SELECT vpb.ne_id, COUNT(DISTINCT vpb.vrf_id) AS vrf_count FROM t_vpn_pe_binding vpb GROUP BY vpb.ne_id

-- 期望SQL:
SELECT ne.ne_name, COUNT(DISTINCT b.vrf_id) AS vrf_count
FROM t_network_element ne
LEFT JOIN t_vpn_pe_binding b ON ne.ne_id = b.ne_id
WHERE ne.role = 'PE'
GROUP BY ne.ne_name
ORDER BY vrf_count DESC, ne.ne_name;
```

---

### Q36 [Medium] 找出每个站点机柜利用率超过80%的站点。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多2行, 缺少2行
**表选择**: 生成=t_site | 期望=t_site
**列选择**: 生成=site_id, site_name, city, used_rack_count, total_rack_count, rack_usage_pct | 期望=site_id, site_name, city, rack_util_pct
**行数**: 生成=2 | 期望=2
**隐性知识**: 机柜利用率是派生指标：used_rack_count / total_rack_count × 100；需防止除零
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT s.site_id, s.site_name, s.city, s.used_rack_count, s.total_rack_count, ROUND(s.used_rack_count * 100.0 / s.total_rack_count, 2) AS rack_usage_pct FROM t_site s WHERE s.total_rack_count > 0 AND s.used_rack_count * 100.0 / s.total_rack_count > 80

-- 期望SQL:
SELECT site_id, site_name, city,
       ROUND(used_rack_count * 100.0 / NULLIF(total_rack_count, 0), 2) AS rack_util_pct
FROM t_site
WHERE total_rack_count IS NOT NULL AND total_rack_count > 0
  AND used_rack_count * 100.0 / NULLIF(total_rack_count, 0) > 80
ORDER BY rack_util_pct DESC, site_name;
```

---

### Q37 [Medium] 查询所有显式路径SRv6 Policy中，SLA目标为LOW_LATENCY且最大时延约束小于10ms的策略。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_srv6_policy | 期望=t_srv6_policy
**列选择**: 生成=policy_id, policy_name, sla_type, max_latency_ms, oper_status | 期望=policy_id, policy_name, source_ne_id, dest_ne_id, max_latency_ms, preference
**行数**: 生成=0 | 期望=0
**隐性知识**: 显式路径策略→explicit_path=TRUE；低时延意图在 sla_type=LOW_LATENCY
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT sp.policy_id, sp.policy_name, sp.sla_type, sp.max_latency_ms, sp.oper_status FROM t_srv6_policy sp WHERE sp.explicit_path AND sp.sla_type = 'LOW_LATENCY' AND sp.max_latency_ms < 10

-- 期望SQL:
SELECT policy_id, policy_name, source_ne_id, dest_ne_id, max_latency_ms, preference
FROM t_srv6_policy
WHERE explicit_path = TRUE
  AND sla_type = 'LOW_LATENCY'
  AND max_latency_ms < 10
ORDER BY max_latency_ms, preference DESC;
```

---

### Q38 [Medium] 查询最近7天内有路径切换的SRv6 Policy。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多13行, 缺少13行
**表选择**: 生成=t_srv6_policy | 期望=t_srv6_policy
**列选择**: 生成=policy_id, policy_name, last_path_change, oper_status | 期望=policy_id, policy_name, source_ne_id, dest_ne_id, last_path_change
**行数**: 生成=13 | 期望=13
**隐性知识**: 路径变化时间在 last_path_change；最近7天按时间过滤
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT sp.policy_id, sp.policy_name, sp.last_path_change, sp.oper_status FROM t_srv6_policy sp WHERE sp.last_path_change >= CURRENT_TIMESTAMP - INTERVAL 7 DAY

-- 期望SQL:
SELECT policy_id, policy_name, source_ne_id, dest_ne_id, last_path_change
FROM t_srv6_policy
WHERE last_path_change >= NOW() - INTERVAL '7 days'
ORDER BY last_path_change DESC;
```

---

### Q39 [Medium] 统计每个隧道类型的隧道数量和平均配置带宽。

**判定**: ✅正确
**原因**: 完全匹配
**表选择**: 生成=t_tunnel | 期望=t_tunnel
**列选择**: 生成=tunnel_type, tunnel_count, avg_bandwidth_mbps | 期望=tunnel_type, tunnel_count, avg_bandwidth_mbps
**行数**: 生成=4 | 期望=4
**隐性知识**: 配置带宽看 t_tunnel.bandwidth_mbps，不是实测吞吐

---

### Q40 [Medium] 查询所有运行状态UP但最新KPI中采样状态为DOWN的接口。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_interface, t_interface_perf_kpi | 期望=t_interface, t_interface_perf_kpi, t_network_element
**列选择**: 生成=if_id, ne_id, if_name, if_oper_status, kpi_oper_status | 期望=if_id, if_name, ne_name, inventory_oper_status, kpi_oper_status
**行数**: 生成=0 | 期望=0
**隐性知识**: 运行状态不一致：基础表 t_interface.oper_status 与最新 KPI 快照对比
**知识缺口**: 返回列不同, JOIN路径错误, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT i.if_id, i.ne_id, i.if_name, i.oper_status AS if_oper_status, k.oper_status AS kpi_oper_status FROM t_interface i JOIN (SELECT if_id, oper_status, ROW_NUMBER() OVER (PARTITION BY if_id ORDER BY collect_time DESC) AS rn FROM t_interface_perf_kpi) k ON i.if_id = k.if_id AND k.rn = 1 WHERE i.oper_status = 'UP' AND k.oper_status = 'DOWN'

-- 期望SQL:
WITH latest AS (
  SELECT if_id, MAX(collect_time) AS max_time
  FROM t_interface_perf_kpi
  GROUP BY if_id
)
SELECT i.if_id, i.if_name, ne.ne_name, i.oper_status AS inventory_oper_status, k.oper_status AS kpi_oper_status
FROM latest l
JOIN t_interface_perf_kpi k ON l.if_id = k.if_id AND l.max_time = k.collect_time
JOIN t_interface i ON k.if_id = i.if_id
JOIN t_network_element ne ON i.ne_id = ne.ne_id
WHERE i.oper_status = 'UP' AND k.oper_status = 'DOWN'
ORDER BY ne.ne_name, i.if_name;
```

---

### Q41 [Hard] 查询过去24小时平均CPU利用率排名前10的PE设备，并同时返回平均内存利用率。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多10行, 缺少10行
**表选择**: 生成=t_ne_perf_kpi, t_network_element | 期望=t_ne_perf_kpi, t_network_element
**列选择**: 生成=ne_id, ne_name, avg_cpu_pct, avg_mem_pct | 期望=ne_name, avg_cpu_pct, avg_mem_pct
**行数**: 生成=10 | 期望=10
**隐性知识**: 排名对象是PE设备；CPU和内存都来自 t_ne_perf_kpi；过去24小时按设备聚合后排序
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT k.ne_id, ne.ne_name, ROUND(AVG(k.cpu_usage_avg_pct), 2) AS avg_cpu_pct, ROUND(AVG(k.memory_usage_avg_pct), 2) AS avg_mem_pct FROM t_ne_perf_kpi k JOIN t_network_element ne ON k.ne_id = ne.ne_id WHERE ne.role = 'PE' AND k.collect_time >= CURRENT_TIMESTAMP - INTERVAL 24 HOUR GROUP BY k.ne_id, ne.ne_name ORDER BY avg_cpu_pct DESC LIMIT 10

-- 期望SQL:
SELECT ne.ne_name,
       ROUND(AVG(k.cpu_usage_avg_pct), 2) AS avg_cpu_pct,
       ROUND(AVG(k.memory_usage_avg_pct), 2) AS avg_mem_pct
FROM t_ne_perf_kpi k
JOIN t_network_element ne ON k.ne_id = ne.ne_id
WHERE ne.role = 'PE'
  AND k.collect_time >= NOW() - INTERVAL '24 hours'
GROUP BY ne.ne_name
ORDER BY avg_cpu_pct DESC, ne.ne_name
LIMIT 10;
```

---

### Q42 [Hard] 找出最近7天内BGP对等体可用率低于80%的设备。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_ne_perf_kpi, t_network_element | 期望=t_ne_perf_kpi, t_network_element
**列选择**: 生成=ne_id, ne_name, bgp_avail_pct | 期望=ne_name, bgp_peer_up_ratio_pct
**行数**: 生成=0 | 期望=0
**隐性知识**: BGP对等体可用率=bgp_peer_up_count / bgp_peer_total_count × 100；按设备和时间窗聚合
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT k.ne_id, ne.ne_name, ROUND(AVG(k.bgp_peer_up_count * 100.0 / k.bgp_peer_total_count), 2) AS bgp_avail_pct FROM t_ne_perf_kpi k JOIN t_network_element ne ON k.ne_id = ne.ne_id WHERE k.collect_time >= CURRENT_TIMESTAMP - INTERVAL 7 DAY AND k.bgp_peer_total_count > 0 GROUP BY k.ne_id, ne.ne_name HAVING AVG(k.bgp_peer_up_count * 100.0 / k.bgp_peer_total_count) < 80

-- 期望SQL:
SELECT ne.ne_name,
       ROUND(AVG(k.bgp_peer_up_count * 100.0 / NULLIF(k.bgp_peer_total_count, 0)), 2) AS bgp_peer_up_ratio_pct
FROM t_ne_perf_kpi k
JOIN t_network_element ne ON k.ne_id = ne.ne_id
WHERE k.collect_time >= NOW() - INTERVAL '7 days'
  AND k.bgp_peer_total_count > 0
GROUP BY ne.ne_name
HAVING AVG(k.bgp_peer_up_count * 100.0 / NULLIF(k.bgp_peer_total_count, 0)) < 80
ORDER BY bgp_peer_up_ratio_pct, ne.ne_name;
```

---

### Q43 [Hard] 统计最近24小时每个区域的关键告警压力：按区域汇总critical+major告警平均值。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多5行, 缺少5行
**表选择**: 生成=t_ne_perf_kpi, t_network_element, t_site | 期望=t_ne_perf_kpi, t_network_element, t_site
**列选择**: 生成=region, avg_critical, avg_major, avg_critical_major | 期望=region, avg_alarm_pressure
**行数**: 生成=5 | 期望=5
**隐性知识**: 告警压力没有现成字段，需要用设备KPI中的 alarm_critical_count + alarm_major_count 派生；区域来自站点
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT s.region, ROUND(AVG(k.alarm_critical_count), 2) AS avg_critical, ROUND(AVG(k.alarm_major_count), 2) AS avg_major, ROUND(AVG(k.alarm_critical_count + k.alarm_major_count), 2) AS avg_critical_major FROM t_ne_perf_kpi k JOIN t_network_element ne ON k.ne_id = ne.ne_id JOIN t_site s ON ne.site_id = s.site_id WHERE k.collect_time >= CURRENT_TIMESTAMP - INTERVAL 24 HOUR GROUP BY s.region

-- 期望SQL:
SELECT s.region,
       ROUND(AVG(k.alarm_critical_count + k.alarm_major_count), 2) AS avg_alarm_pressure
FROM t_ne_perf_kpi k
JOIN t_network_element ne ON k.ne_id = ne.ne_id
JOIN t_site s ON ne.site_id = s.site_id
WHERE k.collect_time >= NOW() - INTERVAL '24 hours'
GROUP BY s.region
ORDER BY avg_alarm_pressure DESC, s.region;
```

---

### Q44 [Hard] 查询最新一个采集周期中入方向带宽利用率和出方向带宽利用率都超过70%的接口。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多21行, 缺少21行
**表选择**: 生成=t_interface_perf_kpi | 期望=t_interface, t_interface_perf_kpi, t_network_element
**列选择**: 生成=if_id, ne_id, in_bandwidth_usage_pct, out_bandwidth_usage_pct | 期望=ne_name, if_name, in_bandwidth_usage_pct, out_bandwidth_usage_pct
**行数**: 生成=21 | 期望=21
**隐性知识**: 双高利用接口→in_bandwidth_usage_pct>70 AND out_bandwidth_usage_pct>70；最新周期先取接口KPI最大时间
**知识缺口**: 返回列不同, JOIN路径错误, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT ik.if_id, ik.ne_id, ik.in_bandwidth_usage_pct, ik.out_bandwidth_usage_pct FROM t_interface_perf_kpi ik INNER JOIN (SELECT if_id, MAX(collect_time) AS max_ct FROM t_interface_perf_kpi GROUP BY if_id) latest ON ik.if_id = latest.if_id AND ik.collect_time = latest.max_ct WHERE ik.in_bandwidth_usage_pct > 70 AND ik.out_bandwidth_usage_pct > 70

-- 期望SQL:
WITH latest_time AS (
  SELECT MAX(collect_time) AS max_time FROM t_interface_perf_kpi
)
SELECT ne.ne_name, i.if_name, k.in_bandwidth_usage_pct, k.out_bandwidth_usage_pct
FROM t_interface_perf_kpi k
JOIN latest_time lt ON k.collect_time = lt.max_time
JOIN t_interface i ON k.if_id = i.if_id
JOIN t_network_element ne ON i.ne_id = ne.ne_id
WHERE k.in_bandwidth_usage_pct > 70 AND k.out_bandwidth_usage_pct > 70
ORDER BY k.out_bandwidth_usage_pct DESC, k.in_bandwidth_usage_pct DESC;
```

---

### Q45 [Hard] 找出最近7天发生CRC错误最多的前5个物理接口。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多5行, 缺少5行
**表选择**: 生成=t_interface, t_interface_perf_kpi | 期望=t_interface, t_interface_perf_kpi, t_network_element
**列选择**: 生成=if_id, if_name, ne_id, total_crc_errors | 期望=ne_name, if_name, crc_errors_7d
**行数**: 生成=5 | 期望=5
**隐性知识**: CRC错误在接口KPI表；物理接口需关联接口表过滤 if_type=PHYSICAL
**知识缺口**: 返回列不同, JOIN路径错误

**SQL对比**:

```sql
-- 生成SQL:
SELECT ik.if_id, i.if_name, ik.ne_id, SUM(ik.crc_error_count) AS total_crc_errors FROM t_interface_perf_kpi ik JOIN t_interface i ON ik.if_id = i.if_id WHERE i.if_type = 'PHYSICAL' AND ik.collect_time >= CURRENT_TIMESTAMP - INTERVAL 7 DAY GROUP BY ik.if_id, i.if_name, ik.ne_id ORDER BY total_crc_errors DESC LIMIT 5

-- 期望SQL:
SELECT ne.ne_name, i.if_name, SUM(k.crc_error_count) AS crc_errors_7d
FROM t_interface_perf_kpi k
JOIN t_interface i ON k.if_id = i.if_id
JOIN t_network_element ne ON i.ne_id = ne.ne_id
WHERE i.if_type = 'PHYSICAL'
  AND k.collect_time >= NOW() - INTERVAL '7 days'
GROUP BY ne.ne_name, i.if_name
ORDER BY crc_errors_7d DESC, ne.ne_name, i.if_name
LIMIT 5;
```

---

### Q46 [Hard] 找出最近7天平均温度超过阈值的单板所属设备。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_board, t_ne_perf_kpi, t_network_element | 期望=t_board, t_ne_perf_kpi, t_network_element
**列选择**: 生成=ne_id, ne_name | 期望=ne_name, avg_temp_c, board_temp_threshold
**行数**: 生成=0 | 期望=0
**隐性知识**: 单板温度阈值在 t_board.temperature_threshold，但观测温度只能从设备KPI温度近似映射到所属设备层
**知识缺口**: 返回列不同, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT DISTINCT b.ne_id, ne.ne_name FROM t_board b JOIN t_network_element ne ON b.ne_id = ne.ne_id JOIN t_ne_perf_kpi k ON k.ne_id = b.ne_id WHERE k.collect_time >= CURRENT_TIMESTAMP - INTERVAL 7 DAY AND b.temperature_threshold IS NOT NULL GROUP BY b.board_id, b.ne_id, ne.ne_name, b.temperature_threshold HAVING AVG(k.temperature_avg_c) > b.temperature_threshold

-- 期望SQL:
SELECT ne.ne_name,
       ROUND(AVG(k.temperature_avg_c), 2) AS avg_temp_c,
       MAX(b.temperature_threshold) AS board_temp_threshold
FROM t_board b
JOIN t_network_element ne ON b.ne_id = ne.ne_id
JOIN t_ne_perf_kpi k ON ne.ne_id = k.ne_id
WHERE b.temperature_threshold IS NOT NULL
  AND k.collect_time >= NOW() - INTERVAL '7 days'
GROUP BY ne.ne_name
HAVING AVG(k.temperature_avg_c) > MAX(b.temperature_threshold)
ORDER BY avg_temp_c DESC;
```

---

### Q47 [Hard] 查询最近30天内合同即将到期（30天内）且月租费排名前10的VPN业务。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_l3vpn_service | 期望=t_l3vpn_service
**列选择**: 生成=vpn_id, vpn_name, customer_name, contract_end_date, monthly_fee | 期望=vpn_id, vpn_name, customer_name, monthly_fee, contract_end_date
**行数**: 生成=0 | 期望=0
**隐性知识**: 高价值续约风险业务=合同30天内到期 + monthly_fee高；按月租费排序取Top10
**知识缺口**: 业务规则缺失

**SQL对比**:

```sql
-- 生成SQL:
SELECT v.vpn_id, v.vpn_name, v.customer_name, v.contract_end_date, v.monthly_fee FROM t_l3vpn_service v WHERE v.contract_end_date >= CURRENT_DATE AND v.contract_end_date <= CURRENT_DATE + INTERVAL 30 DAY ORDER BY v.monthly_fee DESC LIMIT 10

-- 期望SQL:
SELECT vpn_id, vpn_name, customer_name, monthly_fee, contract_end_date
FROM t_l3vpn_service
WHERE contract_end_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'
ORDER BY monthly_fee DESC NULLS LAST, contract_end_date
LIMIT 10;
```

---

### Q48 [Hard] 找出每个客户中带宽最大的那条VPN业务。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多30行, 缺少30行
**表选择**: 生成=t_l3vpn_service | 期望=t_l3vpn_service
**列选择**: 生成=customer_name, vpn_id, vpn_name, bandwidth_mbps | 期望=customer_id, customer_name, vpn_id, vpn_name, bandwidth_mbps
**行数**: 生成=30 | 期望=30
**隐性知识**: 每个客户内部 Top1 业务；以 SLA 保证带宽 bandwidth_mbps 作为业务规模代理
**知识缺口**: 返回列不同, 枚举值/条件缺失, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT v.customer_name, v.vpn_id, v.vpn_name, v.bandwidth_mbps FROM t_l3vpn_service v INNER JOIN (SELECT customer_name, MAX(bandwidth_mbps) AS max_bw FROM t_l3vpn_service GROUP BY customer_name) m ON v.customer_name = m.customer_name AND v.bandwidth_mbps = m.max_bw

-- 期望SQL:
WITH ranked AS (
  SELECT customer_id, customer_name, vpn_id, vpn_name, bandwidth_mbps,
         ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY bandwidth_mbps DESC NULLS LAST, vpn_id) AS rn
  FROM t_l3vpn_service
)
SELECT customer_id, customer_name, vpn_id, vpn_name, bandwidth_mbps
FROM ranked
WHERE rn = 1
ORDER BY bandwidth_mbps DESC NULLS LAST, customer_name;
```

---

### Q49 [Hard] 查询所有Hub-Spoke拓扑中担任HUB角色的PE，以及其承载的VPN数量。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多10行, 缺少10行
**表选择**: 生成=t_l3vpn_service, t_network_element, t_vpn_pe_binding | 期望=t_l3vpn_service, t_network_element, t_vpn_pe_binding
**列选择**: 生成=ne_id, ne_name, vpn_count | 期望=ne_name, hub_vpn_count
**行数**: 生成=10 | 期望=10
**隐性知识**: HUB角色不在设备表，而在绑定表的 pe_role=HUB；承载VPN数量按绑定记录去重统计
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT vpb.ne_id, ne.ne_name, COUNT(DISTINCT vpb.vpn_id) AS vpn_count FROM t_vpn_pe_binding vpb JOIN t_network_element ne ON vpb.ne_id = ne.ne_id JOIN t_l3vpn_service v ON vpb.vpn_id = v.vpn_id WHERE v.topology = 'HUB_SPOKE' AND vpb.pe_role = 'HUB' GROUP BY vpb.ne_id, ne.ne_name

-- 期望SQL:
SELECT ne.ne_name, COUNT(DISTINCT b.vpn_id) AS hub_vpn_count
FROM t_vpn_pe_binding b
JOIN t_l3vpn_service v ON b.vpn_id = v.vpn_id
JOIN t_network_element ne ON b.ne_id = ne.ne_id
WHERE v.topology = 'HUB_SPOKE' AND b.pe_role = 'HUB'
GROUP BY ne.ne_name
ORDER BY hub_vpn_count DESC, ne.ne_name;
```

---

### Q50 [Hard] 统计每个VRF实例的路由利用率，并找出超过80%的VRF。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_vrf_instance | 期望=t_vrf_instance
**列选择**: 生成=vrf_id, ne_id, vrf_name, current_route_count, max_routes, route_usage_pct | 期望=vrf_id, vrf_name, ne_id, route_util_pct
**行数**: 生成=0 | 期望=0
**隐性知识**: VRF路由利用率= current_route_count / max_routes × 100；字段都在 VRF 表中
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT vrf.vrf_id, vrf.ne_id, vrf.vrf_name, vrf.current_route_count, vrf.max_routes, ROUND(vrf.current_route_count * 100.0 / vrf.max_routes, 2) AS route_usage_pct FROM t_vrf_instance vrf WHERE vrf.max_routes > 0 AND vrf.current_route_count * 100.0 / vrf.max_routes > 80

-- 期望SQL:
SELECT vrf_id, vrf_name, ne_id,
       ROUND(current_route_count * 100.0 / NULLIF(max_routes, 0), 2) AS route_util_pct
FROM t_vrf_instance
WHERE max_routes IS NOT NULL AND max_routes > 0
  AND current_route_count * 100.0 / NULLIF(max_routes, 0) > 80
ORDER BY route_util_pct DESC, vrf_name;
```

---

### Q51 [Hard] 找出所有启用了BFD但最近24小时接口状态翻转次数超过3次的接口。

**判定**: ⚠️错误
**原因**: 行数不同: 生成0行 vs 期望4行
**表选择**: 生成=t_interface, t_interface_perf_kpi | 期望=t_interface, t_interface_perf_kpi, t_network_element
**列选择**: 生成=if_id, if_name, ne_id, status_change_count | 期望=ne_name, if_name, flap_count_24h
**行数**: 生成=0 | 期望=4
**隐性知识**: BFD启用在接口表；抖动接口用最近24小时 status_change_count 累加判断
**知识缺口**: 返回列不同, JOIN路径错误, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT i.if_id, i.if_name, i.ne_id, k.status_change_count FROM t_interface i JOIN t_interface_perf_kpi k ON i.if_id = k.if_id WHERE i.bfd_enabled AND k.collect_time >= NOW() - INTERVAL 24 HOUR AND k.status_change_count > 3

-- 期望SQL:
SELECT ne.ne_name, i.if_name, SUM(k.status_change_count) AS flap_count_24h
FROM t_interface i
JOIN t_network_element ne ON i.ne_id = ne.ne_id
JOIN t_interface_perf_kpi k ON i.if_id = k.if_id
WHERE i.bfd_enabled = TRUE
  AND k.collect_time >= NOW() - INTERVAL '24 hours'
GROUP BY ne.ne_name, i.if_name
HAVING SUM(k.status_change_count) > 3
ORDER BY flap_count_24h DESC, ne.ne_name, i.if_name;
```

---

### Q52 [Hard] 查询最近7天每条隧道的平均时延、平均抖动，并按平均时延降序排序。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多40行, 缺少40行
**表选择**: 生成=t_tunnel, t_tunnel_perf_kpi | 期望=t_tunnel, t_tunnel_perf_kpi
**列选择**: 生成=tunnel_id, tunnel_name, avg_latency, avg_jitter | 期望=tunnel_name, avg_latency_ms, avg_jitter_ms
**行数**: 生成=40 | 期望=40
**隐性知识**: 隧道质量统计来自 t_tunnel_perf_kpi；过去7天按 tunnel_id 聚合
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT t.tunnel_id, t.tunnel_name, AVG(k.latency_avg_ms) AS avg_latency, AVG(k.jitter_avg_ms) AS avg_jitter FROM t_tunnel t JOIN t_tunnel_perf_kpi k ON t.tunnel_id = k.tunnel_id WHERE k.collect_time >= NOW() - INTERVAL 7 DAY GROUP BY t.tunnel_id, t.tunnel_name ORDER BY avg_latency DESC

-- 期望SQL:
SELECT t.tunnel_name,
       ROUND(AVG(k.latency_avg_ms), 2) AS avg_latency_ms,
       ROUND(AVG(k.jitter_avg_ms), 2) AS avg_jitter_ms
FROM t_tunnel_perf_kpi k
JOIN t_tunnel t ON k.tunnel_id = t.tunnel_id
WHERE k.collect_time >= NOW() - INTERVAL '7 days'
GROUP BY t.tunnel_name
ORDER BY avg_latency_ms DESC, t.tunnel_name;
```

---

### Q53 [Hard] 找出最新SLA指标已不达标，但四个子项中只有时延不达标的VPN。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多3行, 缺少3行
**表选择**: 生成=t_l3vpn_service, t_vpn_sla_kpi | 期望=t_l3vpn_service, t_vpn_sla_kpi
**列选择**: 生成=vpn_id, vpn_name | 期望=vpn_name, customer_name, e2e_latency_avg_ms, max_latency_ms
**行数**: 生成=3 | 期望=3
**隐性知识**: 综合不达标且仅时延不达标→sla_overall_met=FALSE, sla_latency_met=FALSE，其余三个子项均为TRUE；最新样本按VPN取最新 collect_time
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT v.vpn_id, v.vpn_name FROM t_l3vpn_service v JOIN t_vpn_sla_kpi k ON v.vpn_id = k.vpn_id WHERE k.collect_time = (SELECT MAX(collect_time) FROM t_vpn_sla_kpi k2 WHERE k2.vpn_id = k.vpn_id) AND NOT k.sla_overall_met AND NOT k.sla_latency_met AND k.sla_jitter_met AND k.sla_loss_met AND k.sla_availability_met GROUP BY v.vpn_id, v.vpn_name

-- 期望SQL:
WITH latest AS (
  SELECT vpn_id, MAX(collect_time) AS max_time
  FROM t_vpn_sla_kpi
  GROUP BY vpn_id
)
SELECT v.vpn_name, v.customer_name, s.e2e_latency_avg_ms, v.max_latency_ms
FROM latest l
JOIN t_vpn_sla_kpi s ON l.vpn_id = s.vpn_id AND l.max_time = s.collect_time
JOIN t_l3vpn_service v ON s.vpn_id = v.vpn_id
WHERE s.sla_overall_met = FALSE
  AND s.sla_latency_met = FALSE
  AND s.sla_jitter_met = TRUE
  AND s.sla_loss_met = TRUE
  AND s.sla_availability_met = TRUE
ORDER BY s.e2e_latency_avg...
```

---

### Q54 [Hard] 统计每个区域近7天平均CPU利用率最高的前三台设备。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多15行, 缺少15行
**表选择**: 生成=t_ne_perf_kpi, t_network_element, t_site | 期望=t_ne_perf_kpi, t_network_element, t_site
**列选择**: 生成=region, ne_id, ne_name, avg_cpu | 期望=region, ne_name, avg_cpu
**行数**: 生成=15 | 期望=15
**隐性知识**: 区域内Top3设备，需要先按设备聚合，再做分区排名
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT region, ne_id, ne_name, avg_cpu FROM (SELECT s.region, n.ne_id, n.ne_name, AVG(k.cpu_usage_avg_pct) AS avg_cpu, ROW_NUMBER() OVER (PARTITION BY s.region ORDER BY AVG(k.cpu_usage_avg_pct) DESC) AS rn FROM t_network_element n JOIN t_site s ON n.site_id = s.site_id JOIN t_ne_perf_kpi k ON n.ne_id = k.ne_id WHERE k.collect_time >= NOW() - INTERVAL 7 DAY GROUP BY s.region, n.ne_id, n.ne_name) t WHERE rn <= 3

-- 期望SQL:
WITH device_avg AS (
  SELECT s.region, ne.ne_name, AVG(k.cpu_usage_avg_pct) AS avg_cpu
  FROM t_ne_perf_kpi k
  JOIN t_network_element ne ON k.ne_id = ne.ne_id
  JOIN t_site s ON ne.site_id = s.site_id
  WHERE k.collect_time >= NOW() - INTERVAL '7 days'
  GROUP BY s.region, ne.ne_name
), ranked AS (
  SELECT region, ne_name, avg_cpu,
         ROW_NUMBER() OVER (PARTITION BY region ORDER BY avg_cpu DESC, ne_name) AS rn
  FROM device_avg
)
SELECT region, ne_name, ROUND(avg_cpu, 2) AS avg_cpu
FROM...
```

---

### Q55 [Hard] 找出同一客户名下同时使用SRV6_TE和MPLS_TE两种承载方式的客户。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列一致)
**表选择**: 生成=t_l3vpn_service | 期望=t_l3vpn_service
**列选择**: 生成=customer_id, customer_name | 期望=customer_id, customer_name
**行数**: 生成=0 | 期望=0
**隐性知识**: 同一客户多承载策略是组合概念，需要对 underlay_type 做条件聚合
**知识缺口**: 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT a.customer_id, a.customer_name FROM t_l3vpn_service a WHERE a.underlay_type = 'SRV6_TE' INTERSECT SELECT b.customer_id, b.customer_name FROM t_l3vpn_service b WHERE b.underlay_type = 'MPLS_TE'

-- 期望SQL:
SELECT customer_id, customer_name
FROM t_l3vpn_service
GROUP BY customer_id, customer_name
HAVING COUNT(DISTINCT CASE WHEN underlay_type IN ('SRV6_TE', 'MPLS_TE') THEN underlay_type END) = 2
ORDER BY customer_name;
```

---

### Q56 [Hard] 查询每个PE设备最近24小时平均接口出方向带宽利用率。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多18行, 缺少18行
**表选择**: 生成=t_interface_perf_kpi, t_network_element | 期望=t_interface_perf_kpi, t_network_element
**列选择**: 生成=ne_id, ne_name, avg_out_bw_pct | 期望=ne_name, avg_out_bw_pct
**行数**: 生成=18 | 期望=18
**隐性知识**: PE设备接口利用率通过接口KPI按设备聚合；默认看出方向 out_bandwidth_usage_pct
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT n.ne_id, n.ne_name, AVG(k.out_bandwidth_usage_pct) AS avg_out_bw_pct FROM t_network_element n JOIN t_interface_perf_kpi k ON n.ne_id = k.ne_id WHERE n.role = 'PE' AND k.collect_time >= NOW() - INTERVAL 24 HOUR GROUP BY n.ne_id, n.ne_name

-- 期望SQL:
SELECT ne.ne_name, ROUND(AVG(k.out_bandwidth_usage_pct), 2) AS avg_out_bw_pct
FROM t_interface_perf_kpi k
JOIN t_network_element ne ON k.ne_id = ne.ne_id
WHERE ne.role = 'PE'
  AND k.collect_time >= NOW() - INTERVAL '24 hours'
GROUP BY ne.ne_name
ORDER BY avg_out_bw_pct DESC, ne.ne_name;
```

---

### Q57 [Hard] 找出最近7天平均丢包率超过其SLA上限的VPN业务。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多12行, 缺少12行
**表选择**: 生成=t_l3vpn_service, t_vpn_sla_kpi | 期望=t_l3vpn_service, t_vpn_sla_kpi
**列选择**: 生成=vpn_id, vpn_name, avg_loss, max_packet_loss_pct | 期望=vpn_name, customer_name, avg_loss_pct, sla_loss_pct
**行数**: 生成=12 | 期望=12
**隐性知识**: SLA上限取 t_l3vpn_service.max_packet_loss_pct；实际值取 t_vpn_sla_kpi.e2e_packet_loss_pct 的7天平均
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT v.vpn_id, v.vpn_name, AVG(k.e2e_packet_loss_pct) AS avg_loss, v.max_packet_loss_pct FROM t_l3vpn_service v JOIN t_vpn_sla_kpi k ON v.vpn_id = k.vpn_id WHERE k.collect_time >= NOW() - INTERVAL 7 DAY GROUP BY v.vpn_id, v.vpn_name, v.max_packet_loss_pct HAVING AVG(k.e2e_packet_loss_pct) > v.max_packet_loss_pct

-- 期望SQL:
SELECT v.vpn_name, v.customer_name,
       ROUND(AVG(s.e2e_packet_loss_pct), 4) AS avg_loss_pct,
       v.max_packet_loss_pct AS sla_loss_pct
FROM t_vpn_sla_kpi s
JOIN t_l3vpn_service v ON s.vpn_id = v.vpn_id
WHERE s.collect_time >= NOW() - INTERVAL '7 days'
GROUP BY v.vpn_name, v.customer_name, v.max_packet_loss_pct
HAVING AVG(s.e2e_packet_loss_pct) > v.max_packet_loss_pct
ORDER BY avg_loss_pct DESC, v.vpn_name;
```

---

### Q58 [Hard] 找出没有任何接入绑定记录的ACTIVE VPN业务。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多8行, 缺少8行
**表选择**: 生成=t_l3vpn_service, t_vpn_pe_binding | 期望=t_l3vpn_service, t_vpn_pe_binding
**列选择**: 生成=vpn_id, vpn_name | 期望=vpn_id, vpn_name, customer_name
**行数**: 生成=8 | 期望=8
**隐性知识**: 没有接入绑定=在 t_vpn_pe_binding 中不存在 vpn_id 记录；是 anti-join 场景
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT v.vpn_id, v.vpn_name FROM t_l3vpn_service v WHERE v.admin_status = 'ACTIVE' AND NOT EXISTS (SELECT 1 FROM t_vpn_pe_binding b WHERE b.vpn_id = v.vpn_id)

-- 期望SQL:
SELECT v.vpn_id, v.vpn_name, v.customer_name
FROM t_l3vpn_service v
WHERE v.admin_status = 'ACTIVE'
  AND NOT EXISTS (
    SELECT 1 FROM t_vpn_pe_binding b WHERE b.vpn_id = v.vpn_id
  )
ORDER BY v.customer_name, v.vpn_name;
```

---

### Q59 [Hard] 查询所有配置了Tunnel Policy但没有配置RT导入导出的VRF实例。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_vrf_instance | 期望=t_vrf_instance
**列选择**: 生成=vrf_id, vrf_name, tunnel_policy, vpn_target_import, vpn_target_export | 期望=vrf_id, vrf_name, ne_id, tunnel_policy, vpn_target_import, vpn_target_export
**行数**: 生成=0 | 期望=0
**隐性知识**: VRF配置缺失检查：tunnel_policy 非空，但 vpn_target_import 或 vpn_target_export 为空
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT vr.vrf_id, vr.vrf_name, vr.tunnel_policy, vr.vpn_target_import, vr.vpn_target_export FROM t_vrf_instance vr WHERE vr.tunnel_policy IS NOT NULL AND vr.tunnel_policy != '' AND (vr.vpn_target_import IS NULL OR vr.vpn_target_import = '' OR vr.vpn_target_export IS NULL OR vr.vpn_target_export = '')

-- 期望SQL:
SELECT vrf_id, vrf_name, ne_id, tunnel_policy, vpn_target_import, vpn_target_export
FROM t_vrf_instance
WHERE tunnel_policy IS NOT NULL
  AND (vpn_target_import IS NULL OR vpn_target_export IS NULL)
ORDER BY vrf_name;
```

---

### Q60 [Hard] 查询每个厂商最近7天设备平均内存利用率，并按从高到低排序。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多4行, 缺少4行
**表选择**: 生成=t_ne_perf_kpi, t_network_element | 期望=t_ne_perf_kpi, t_network_element
**列选择**: 生成=vendor, avg_mem | 期望=vendor, avg_mem_pct
**行数**: 生成=4 | 期望=4
**隐性知识**: 设备健康按厂商聚合；指标取 t_ne_perf_kpi.memory_usage_avg_pct
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT n.vendor, AVG(k.memory_usage_avg_pct) AS avg_mem FROM t_network_element n JOIN t_ne_perf_kpi k ON n.ne_id = k.ne_id WHERE k.collect_time >= NOW() - INTERVAL 7 DAY GROUP BY n.vendor ORDER BY avg_mem DESC

-- 期望SQL:
SELECT ne.vendor, ROUND(AVG(k.memory_usage_avg_pct), 2) AS avg_mem_pct
FROM t_ne_perf_kpi k
JOIN t_network_element ne ON k.ne_id = ne.ne_id
WHERE k.collect_time >= NOW() - INTERVAL '7 days'
GROUP BY ne.vendor
ORDER BY avg_mem_pct DESC, ne.vendor;
```

---

### Q61 [Extra Hard] 查询最近30天每个客户的SLA达标率，并只保留达标率低于95%的客户。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多30行, 缺少30行
**表选择**: 生成=t_l3vpn_service, t_vpn_sla_kpi | 期望=t_l3vpn_service, t_vpn_sla_kpi
**列选择**: 生成=customer_id, customer_name, sla_met_pct | 期望=customer_id, customer_name, sla_hit_rate_pct, total_samples
**行数**: 生成=30 | 期望=30
**隐性知识**: 达标率= sla_overall_met=TRUE 的样本数 / 总样本数；客户维度需通过 VPN 表映射
**知识缺口**: 返回列不同, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT v.customer_id, v.customer_name, AVG(CASE WHEN k.sla_overall_met THEN 1.0 ELSE 0.0 END) * 100 AS sla_met_pct FROM t_l3vpn_service v JOIN t_vpn_sla_kpi k ON v.vpn_id = k.vpn_id WHERE k.collect_time >= NOW() - INTERVAL 30 DAY GROUP BY v.customer_id, v.customer_name HAVING AVG(CASE WHEN k.sla_overall_met THEN 1.0 ELSE 0.0 END) * 100 < 95

-- 期望SQL:
WITH customer_sla AS (
  SELECT v.customer_id, v.customer_name,
         COUNT(*) AS total_samples,
         SUM(CASE WHEN s.sla_overall_met THEN 1 ELSE 0 END) AS met_samples
  FROM t_vpn_sla_kpi s
  JOIN t_l3vpn_service v ON s.vpn_id = v.vpn_id
  WHERE s.collect_time >= NOW() - INTERVAL '30 days'
  GROUP BY v.customer_id, v.customer_name
)
SELECT customer_id, customer_name,
       ROUND(met_samples * 100.0 / NULLIF(total_samples, 0), 2) AS sla_hit_rate_pct,
       total_samples
FROM customer_sl...
```

---

### Q62 [Extra Hard] 找出最近7天中每天都有SLA违规样本的VPN业务。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_l3vpn_service, t_vpn_sla_kpi | 期望=t_l3vpn_service, t_vpn_sla_kpi
**列选择**: 生成=vpn_id, vpn_name | 期望=vpn_id, vpn_name, customer_name
**行数**: 生成=0 | 期望=0
**隐性知识**: 每天都有SLA违规=最近7个自然日内每天至少出现1个 sla_overall_met=FALSE 样本
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT v.vpn_id, v.vpn_name FROM t_l3vpn_service v JOIN t_vpn_sla_kpi k ON v.vpn_id = k.vpn_id WHERE k.collect_time >= NOW() - INTERVAL 7 DAY AND NOT k.sla_overall_met GROUP BY v.vpn_id, v.vpn_name HAVING COUNT(DISTINCT CAST(k.collect_time AS DATE)) = 7

-- 期望SQL:
WITH daily_violation AS (
  SELECT vpn_id, DATE(collect_time) AS d
  FROM t_vpn_sla_kpi
  WHERE collect_time >= CURRENT_DATE - INTERVAL '6 days'
    AND sla_overall_met = FALSE
  GROUP BY vpn_id, DATE(collect_time)
)
SELECT v.vpn_id, v.vpn_name, v.customer_name
FROM daily_violation dv
JOIN t_l3vpn_service v ON dv.vpn_id = v.vpn_id
GROUP BY v.vpn_id, v.vpn_name, v.customer_name
HAVING COUNT(*) = 7
ORDER BY v.customer_name, v.vpn_name;
```

---

### Q63 [Extra Hard] 计算每台PE设备最近7天的综合健康分：CPU、内存、温度、告警四项各25分，要求输出低于60分的设备。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_ne_perf_kpi, t_network_element | 期望=t_ne_perf_kpi, t_network_element
**列选择**: 生成=ne_id, ne_name, health_score | 期望=ne_name, health_score, avg_cpu, avg_mem, avg_temp, avg_alarm_pressure
**行数**: 生成=0 | 期望=0
**隐性知识**: 设备健康分是自定义规则：CPU<70、内存<75、温度<60、重大+严重告警均值<5 各得25分
**知识缺口**: 返回列不同, 业务规则缺失

**SQL对比**:

```sql
-- 生成SQL:
SELECT ne_id, ne_name, health_score FROM (SELECT n.ne_id, n.ne_name, 25 * (1 - AVG(k.cpu_usage_avg_pct) / 100.0) + 25 * (1 - AVG(k.memory_usage_avg_pct) / 100.0) + 25 * CASE WHEN AVG(k.temperature_avg_c) <= 45 THEN 1.0 WHEN AVG(k.temperature_avg_c) >= 85 THEN 0.0 ELSE (85 - AVG(k.temperature_avg_c)) / 40.0 END + 25 * CASE WHEN AVG(k.alarm_critical_count + k.alarm_major_count) = 0 THEN 1.0 WHEN AVG(k.alarm_critical_count + k.alarm_major_count) >= 10 THEN 0.0 ELSE (10 - AVG(k.alarm_critical_count ...

-- 期望SQL:
WITH agg AS (
  SELECT ne.ne_id, ne.ne_name,
         AVG(k.cpu_usage_avg_pct) AS avg_cpu,
         AVG(k.memory_usage_avg_pct) AS avg_mem,
         AVG(k.temperature_avg_c) AS avg_temp,
         AVG(k.alarm_critical_count + k.alarm_major_count) AS avg_alarm_pressure
  FROM t_ne_perf_kpi k
  JOIN t_network_element ne ON k.ne_id = ne.ne_id
  WHERE ne.role = 'PE'
    AND k.collect_time >= NOW() - INTERVAL '7 days'
  GROUP BY ne.ne_id, ne.ne_name
)
SELECT ne_name,
       (CASE WHEN avg_cpu < 70 THE...
```

---

### Q64 [Extra Hard] 找出最近24小时流量增长最快的前10个接口（对比前24小时平均出方向利用率）。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多10行, 缺少10行
**表选择**: 生成=t_interface_perf_kpi | 期望=t_interface, t_interface_perf_kpi, t_network_element
**列选择**: 生成=if_id, ne_id, current_avg, previous_avg, growth | 期望=ne_name, if_name, current_avg_pct, previous_avg_pct, growth_pct_point
**行数**: 生成=10 | 期望=10
**隐性知识**: 增长最快=最近24h平均 out_bandwidth_usage_pct - 再前24h平均；这是双时间窗对比模式
**知识缺口**: 返回列不同, JOIN路径错误, 枚举值/条件缺失, 时间窗口处理

**SQL对比**:

```sql
-- 生成SQL:
SELECT cur.if_id, cur.ne_id, cur.avg_out AS current_avg, prev.avg_out AS previous_avg, cur.avg_out - prev.avg_out AS growth FROM (SELECT if_id, ne_id, AVG(out_bandwidth_usage_pct) AS avg_out FROM t_interface_perf_kpi WHERE collect_time >= NOW() - INTERVAL 24 HOUR GROUP BY if_id, ne_id) cur JOIN (SELECT if_id, AVG(out_bandwidth_usage_pct) AS avg_out FROM t_interface_perf_kpi WHERE collect_time >= NOW() - INTERVAL 48 HOUR AND collect_time < NOW() - INTERVAL 24 HOUR GROUP BY if_id) prev ON cur.if_i...

-- 期望SQL:
WITH bucketed AS (
  SELECT if_id,
         CASE WHEN collect_time >= NOW() - INTERVAL '24 hours' THEN 'CUR'
              WHEN collect_time >= NOW() - INTERVAL '48 hours' THEN 'PRE' END AS win,
         AVG(out_bandwidth_usage_pct) AS avg_out_bw
  FROM t_interface_perf_kpi
  WHERE collect_time >= NOW() - INTERVAL '48 hours'
  GROUP BY if_id,
           CASE WHEN collect_time >= NOW() - INTERVAL '24 hours' THEN 'CUR'
                WHEN collect_time >= NOW() - INTERVAL '48 hours' THEN 'PRE' END...
```

---

### Q65 [Extra Hard] 找出那些最新SLA指标已不达标，但其承载隧道最新KPI仍显示sla_violation=FALSE的VPN。

**判定**: ⚠️错误
**原因**: 行数不同: 生成9行 vs 期望25行
**表选择**: 生成=t_l3vpn_service, t_tunnel, t_tunnel_perf_kpi, t_vpn_sla_kpi | 期望=t_l3vpn_service, t_tunnel, t_tunnel_perf_kpi, t_vpn_sla_kpi
**列选择**: 生成=vpn_id, vpn_name | 期望=vpn_name, tunnel_name, sla_overall_met, sla_violation
**行数**: 生成=9 | 期望=25
**隐性知识**: 跨层不一致：业务层SLA不达标，但底层隧道层未报违规；用 associated_vpn_ids 文本包含 vpn_id 近似表示弱关联
**知识缺口**: 返回列不同, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT DISTINCT v.vpn_id, v.vpn_name FROM t_l3vpn_service v JOIN t_vpn_sla_kpi sk ON v.vpn_id = sk.vpn_id JOIN t_tunnel tu ON tu.associated_vpn_ids LIKE '%' || CAST(v.vpn_id AS VARCHAR) || '%' JOIN t_tunnel_perf_kpi tk ON tu.tunnel_id = tk.tunnel_id WHERE sk.collect_time = (SELECT MAX(collect_time) FROM t_vpn_sla_kpi sk2 WHERE sk2.vpn_id = v.vpn_id) AND tk.collect_time = (SELECT MAX(collect_time) FROM t_tunnel_perf_kpi tk2 WHERE tk2.tunnel_id = tu.tunnel_id) AND NOT sk.sla_overall_met AND NOT tk...

-- 期望SQL:
WITH latest_vpn AS (
  SELECT vpn_id, MAX(collect_time) AS max_time
  FROM t_vpn_sla_kpi
  GROUP BY vpn_id
), latest_tunnel AS (
  SELECT tunnel_id, MAX(collect_time) AS max_time
  FROM t_tunnel_perf_kpi
  GROUP BY tunnel_id
)
SELECT DISTINCT v.vpn_name, t.tunnel_name, sk.sla_overall_met, tk.sla_violation
FROM latest_vpn lv
JOIN t_vpn_sla_kpi sk ON lv.vpn_id = sk.vpn_id AND lv.max_time = sk.collect_time
JOIN t_l3vpn_service v ON sk.vpn_id = v.vpn_id
JOIN t_tunnel t ON t.associated_vpn_ids LIKE C...
```

---

### Q66 [Extra Hard] 找出最近7天路径切换次数最多且同时发生SLA违规的前5条隧道。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多5行, 缺少5行
**表选择**: 生成=t_tunnel, t_tunnel_perf_kpi | 期望=t_tunnel, t_tunnel_perf_kpi
**列选择**: 生成=tunnel_id, tunnel_name, total_path_changes, violation_count | 期望=tunnel_name, total_path_changes, violation_samples
**行数**: 生成=5 | 期望=5
**隐性知识**: 高风险隧道=path_change_count多且 sla_violation=TRUE；按7天累计切换次数排序
**知识缺口**: 返回列不同, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT tu.tunnel_id, tu.tunnel_name, SUM(tk.path_change_count) AS total_path_changes, COUNT(CASE WHEN tk.sla_violation THEN 1 END) AS violation_count FROM t_tunnel tu JOIN t_tunnel_perf_kpi tk ON tu.tunnel_id = tk.tunnel_id WHERE tk.collect_time >= NOW() - INTERVAL 7 DAY AND tk.sla_violation GROUP BY tu.tunnel_id, tu.tunnel_name ORDER BY total_path_changes DESC LIMIT 5

-- 期望SQL:
SELECT t.tunnel_name,
       SUM(k.path_change_count) AS total_path_changes,
       SUM(CASE WHEN k.sla_violation THEN 1 ELSE 0 END) AS violation_samples
FROM t_tunnel_perf_kpi k
JOIN t_tunnel t ON k.tunnel_id = t.tunnel_id
WHERE k.collect_time >= NOW() - INTERVAL '7 days'
GROUP BY t.tunnel_name
HAVING SUM(CASE WHEN k.sla_violation THEN 1 ELSE 0 END) > 0
ORDER BY total_path_changes DESC, violation_samples DESC, t.tunnel_name
LIMIT 5;
```

---

### Q67 [Extra Hard] 统计每个区域内PLATINUM业务的平均SLA达标率。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多5行, 缺少5行
**表选择**: 生成=t_l3vpn_service, t_network_element, t_site, t_vpn_pe_binding, t_vpn_sla_kpi | 期望=t_l3vpn_service, t_network_element, t_site, t_vpn_pe_binding, t_vpn_sla_kpi
**列选择**: 生成=region, avg_sla_met_pct | 期望=region, avg_sla_hit_rate_pct
**行数**: 生成=5 | 期望=5
**隐性知识**: 区域不是VPN直接字段，需从 VPN→PE绑定→设备→站点 推出业务所属区域；按绑定站点区域关联
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT s.region, AVG(CASE WHEN k.sla_overall_met THEN 1.0 ELSE 0.0 END) * 100 AS avg_sla_met_pct FROM t_l3vpn_service v JOIN t_vpn_sla_kpi k ON v.vpn_id = k.vpn_id JOIN t_vpn_pe_binding b ON v.vpn_id = b.vpn_id JOIN t_network_element n ON b.ne_id = n.ne_id JOIN t_site s ON n.site_id = s.site_id WHERE v.service_level = 'PLATINUM' GROUP BY s.region

-- 期望SQL:
WITH region_vpn AS (
  SELECT DISTINCT v.vpn_id, s.region
  FROM t_l3vpn_service v
  JOIN t_vpn_pe_binding b ON v.vpn_id = b.vpn_id
  JOIN t_network_element ne ON b.ne_id = ne.ne_id
  JOIN t_site s ON ne.site_id = s.site_id
  WHERE v.service_level = 'PLATINUM'
), hit_rate AS (
  SELECT vpn_id,
         AVG(CASE WHEN sla_overall_met THEN 1.0 ELSE 0.0 END) AS hit_rate
  FROM t_vpn_sla_kpi
  GROUP BY vpn_id
)
SELECT rv.region, ROUND(AVG(hr.hit_rate) * 100, 2) AS avg_sla_hit_rate_pct
FROM region_vpn...
```

---

### Q68 [Extra Hard] 找出接入协议为EBGP且CE AS号重复出现在多个不同客户VPN中的情况。

**判定**: ✅正确
**原因**: 完全匹配
**表选择**: 生成=t_l3vpn_service, t_vpn_pe_binding | 期望=t_l3vpn_service, t_vpn_pe_binding
**列选择**: 生成=ce_as_number, customer_count, vpn_count | 期望=ce_as_number, customer_count, vpn_count
**行数**: 生成=3 | 期望=3
**隐性知识**: CE AS号复用风险：相同 ce_as_number 出现在多个不同 customer_id 的 EBGP 接入记录中

---

### Q69 [Extra Hard] 查询每个客户在最近30天的平均月化丢包风险，定义为平均丢包率 × 业务月租费。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多30行, 缺少30行
**表选择**: 生成=t_l3vpn_service, t_vpn_sla_kpi | 期望=t_l3vpn_service, t_vpn_sla_kpi
**列选择**: 生成=customer_id, customer_name, avg_monthly_loss_risk | 期望=customer_id, customer_name, loss_fee_risk
**行数**: 生成=30 | 期望=30
**隐性知识**: 月化丢包风险是自定义风险指标：AVG(e2e_packet_loss_pct) * monthly_fee
**知识缺口**: 返回列不同, 业务规则缺失

**SQL对比**:

```sql
-- 生成SQL:
SELECT v.customer_id, v.customer_name, AVG(k.e2e_packet_loss_pct) * AVG(v.monthly_fee) AS avg_monthly_loss_risk FROM t_l3vpn_service v JOIN t_vpn_sla_kpi k ON v.vpn_id = k.vpn_id WHERE k.collect_time >= NOW() - INTERVAL 30 DAY GROUP BY v.customer_id, v.customer_name

-- 期望SQL:
SELECT v.customer_id, v.customer_name,
       ROUND(AVG(s.e2e_packet_loss_pct * v.monthly_fee), 4) AS loss_fee_risk
FROM t_vpn_sla_kpi s
JOIN t_l3vpn_service v ON s.vpn_id = v.vpn_id
WHERE s.collect_time >= NOW() - INTERVAL '30 days'
GROUP BY v.customer_id, v.customer_name
ORDER BY loss_fee_risk DESC, v.customer_name;
```

---

### Q70 [Extra Hard] 找出所有同时满足以下条件的PE：启用SRv6、存在LOW_LATENCY Policy、且最近7天平均CPU超过70%。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_ne_perf_kpi, t_network_element, t_srv6_policy | 期望=t_ne_perf_kpi, t_network_element, t_srv6_policy
**列选择**: 生成=ne_id, ne_name | 期望=ne_name
**行数**: 生成=0 | 期望=0
**隐性知识**: 复合健康/能力筛选：基础能力来自设备表，策略意图来自 SRv6 Policy，负载来自 NE KPI
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT n.ne_id, n.ne_name FROM t_network_element n WHERE n.srv6_enabled AND n.role = 'PE' AND EXISTS (SELECT 1 FROM t_srv6_policy p WHERE p.source_ne_id = n.ne_id AND p.sla_type = 'LOW_LATENCY') AND EXISTS (SELECT 1 FROM t_ne_perf_kpi k WHERE k.ne_id = n.ne_id AND k.collect_time >= NOW() - INTERVAL 7 DAY GROUP BY k.ne_id HAVING AVG(k.cpu_usage_avg_pct) > 70)

-- 期望SQL:
SELECT DISTINCT ne.ne_name
FROM t_network_element ne
JOIN t_srv6_policy sp ON sp.source_ne_id = ne.ne_id
JOIN t_ne_perf_kpi k ON k.ne_id = ne.ne_id
WHERE ne.role = 'PE'
  AND ne.srv6_enabled = TRUE
  AND sp.sla_type = 'LOW_LATENCY'
  AND k.collect_time >= NOW() - INTERVAL '7 days'
GROUP BY ne.ne_name
HAVING AVG(k.cpu_usage_avg_pct) > 70
ORDER BY ne.ne_name;
```

---

### Q71 [Medium] 查询所有使用QINQ封装的VPN接入绑定及其客户信息。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多32行, 缺少32行
**表选择**: 生成=t_l3vpn_service, t_vpn_pe_binding | 期望=t_l3vpn_service, t_vpn_pe_binding
**列选择**: 生成=binding_id, vpn_id, vpn_name, customer_id, customer_name, ne_id, if_id, encapsulation | 期望=binding_id, customer_name, vpn_name, if_id, vlan_id
**行数**: 生成=32 | 期望=32
**隐性知识**: QINQ封装在 binding.encapsulation 字段；客户信息来自 VPN 表
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT b.binding_id, b.vpn_id, v.vpn_name, v.customer_id, v.customer_name, b.ne_id, b.if_id, b.encapsulation FROM t_vpn_pe_binding b JOIN t_l3vpn_service v ON b.vpn_id = v.vpn_id WHERE b.encapsulation = 'QINQ'

-- 期望SQL:
SELECT b.binding_id, v.customer_name, v.vpn_name, b.if_id, b.vlan_id
FROM t_vpn_pe_binding b
JOIN t_l3vpn_service v ON b.vpn_id = v.vpn_id
WHERE b.encapsulation = 'QINQ'
ORDER BY v.customer_name, b.binding_id;
```

---

### Q72 [Medium] 统计每个站点拥有的设备数量、物理链路端点数量。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多25行, 缺少25行
**表选择**: 生成=t_network_element, t_physical_link, t_site | 期望=t_network_element, t_physical_link, t_site
**列选择**: 生成=site_id, site_name, ne_count, link_count | 期望=site_name, ne_count, link_end_count
**行数**: 生成=25 | 期望=25
**隐性知识**: 站点设备数来自 t_network_element；链路端点数量等于物理链路中该站点出现在 a_site_id 或 z_site_id 的次数
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT s.site_id, s.site_name, COUNT(DISTINCT n.ne_id) AS ne_count, COUNT(DISTINCT pl.link_id) AS link_count FROM t_site s LEFT JOIN t_network_element n ON s.site_id = n.site_id LEFT JOIN t_physical_link pl ON s.site_id = pl.a_site_id OR s.site_id = pl.z_site_id GROUP BY s.site_id, s.site_name

-- 期望SQL:
WITH site_ne AS (
  SELECT site_id, COUNT(*) AS ne_count
  FROM t_network_element
  GROUP BY site_id
), site_link_end AS (
  SELECT site_id, COUNT(*) AS link_end_count
  FROM (
    SELECT a_site_id AS site_id FROM t_physical_link
    UNION ALL
    SELECT z_site_id AS site_id FROM t_physical_link
  ) x
  GROUP BY site_id
)
SELECT s.site_name,
       COALESCE(n.ne_count, 0) AS ne_count,
       COALESCE(l.link_end_count, 0) AS link_end_count
FROM t_site s
LEFT JOIN site_ne n ON s.site_id = n.site_i...
```

---

### Q73 [Medium] 查询每台设备最近一次采集的风扇转速。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多50行, 缺少50行
**表选择**: 生成=t_ne_perf_kpi, t_network_element | 期望=t_ne_perf_kpi, t_network_element
**列选择**: 生成=ne_id, ne_name, fan_speed_rpm, collect_time | 期望=ne_name, fan_speed_rpm, collect_time
**行数**: 生成=50 | 期望=50
**隐性知识**: 最近一次采集按设备取 MAX(collect_time)；风扇转速字段在 t_ne_perf_kpi.fan_speed_rpm
**知识缺口**: 返回列不同, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT k.ne_id, n.ne_name, k.fan_speed_rpm, k.collect_time FROM t_ne_perf_kpi k JOIN t_network_element n ON k.ne_id = n.ne_id WHERE k.collect_time = (SELECT MAX(k2.collect_time) FROM t_ne_perf_kpi k2 WHERE k2.ne_id = k.ne_id)

-- 期望SQL:
WITH latest AS (
  SELECT ne_id, MAX(collect_time) AS max_time
  FROM t_ne_perf_kpi
  GROUP BY ne_id
)
SELECT ne.ne_name, k.fan_speed_rpm, k.collect_time
FROM latest l
JOIN t_ne_perf_kpi k ON l.ne_id = k.ne_id AND l.max_time = k.collect_time
JOIN t_network_element ne ON k.ne_id = ne.ne_id
ORDER BY ne.ne_name;
```

---

### Q74 [Medium] 找出每条物理链路两端属于不同厂商的链路。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多69行, 缺少69行
**表选择**: 生成=t_network_element, t_physical_link | 期望=t_network_element, t_physical_link
**列选择**: 生成=link_id, link_name, a_ne_id, a_vendor, z_ne_id, z_vendor | 期望=link_id, link_name, a_vendor, z_vendor
**行数**: 生成=69 | 期望=69
**隐性知识**: 异厂商链路要同时看 A/Z 两端网元的 vendor
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT pl.link_id, pl.link_name, a.ne_id AS a_ne_id, a.vendor AS a_vendor, z.ne_id AS z_ne_id, z.vendor AS z_vendor FROM t_physical_link pl JOIN t_network_element a ON pl.a_ne_id = a.ne_id JOIN t_network_element z ON pl.z_ne_id = z.ne_id WHERE a.vendor != z.vendor

-- 期望SQL:
SELECT pl.link_id, pl.link_name, na.vendor AS a_vendor, nz.vendor AS z_vendor
FROM t_physical_link pl
JOIN t_network_element na ON pl.a_ne_id = na.ne_id
JOIN t_network_element nz ON pl.z_ne_id = nz.ne_id
WHERE na.vendor <> nz.vendor
ORDER BY pl.link_id;
```

---

### Q75 [Medium] 查询所有PE-CE之间使用OSPF接入的绑定记录。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多22行, 缺少22行
**表选择**: 生成=t_vpn_pe_binding | 期望=t_l3vpn_service, t_network_element, t_vpn_pe_binding
**列选择**: 生成=binding_id, vpn_id, ne_id, vrf_id, if_id, ce_as_number, site_name | 期望=binding_id, vpn_name, ne_name, if_id, routing_protocol
**行数**: 生成=22 | 期望=22
**隐性知识**: PE-CE接入协议看 binding.routing_protocol；不是设备全局 OSPF 状态
**知识缺口**: 返回列不同, JOIN路径错误

**SQL对比**:

```sql
-- 生成SQL:
SELECT b.binding_id, b.vpn_id, b.ne_id, b.vrf_id, b.if_id, b.ce_as_number, b.site_name FROM t_vpn_pe_binding b WHERE b.routing_protocol = 'OSPF'

-- 期望SQL:
SELECT b.binding_id, v.vpn_name, ne.ne_name, b.if_id, b.routing_protocol
FROM t_vpn_pe_binding b
JOIN t_l3vpn_service v ON b.vpn_id = v.vpn_id
JOIN t_network_element ne ON b.ne_id = ne.ne_id
WHERE b.routing_protocol = 'OSPF'
ORDER BY b.binding_id;
```

---

### Q76 [Medium] 查询所有没有板卡信息的设备。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_board, t_network_element | 期望=t_board, t_network_element
**列选择**: 生成=ne_id, ne_name | 期望=ne_id, ne_name, vendor, model
**行数**: 生成=0 | 期望=0
**隐性知识**: 没有板卡信息=在 t_board 中不存在 ne_id 记录；是库存完整性检查
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT n.ne_id, n.ne_name FROM t_network_element n LEFT JOIN t_board b ON n.ne_id = b.ne_id WHERE b.board_id IS NULL

-- 期望SQL:
SELECT ne.ne_id, ne.ne_name, ne.vendor, ne.model
FROM t_network_element ne
WHERE NOT EXISTS (
  SELECT 1 FROM t_board b WHERE b.ne_id = ne.ne_id
)
ORDER BY ne.ne_name;
```

---

### Q77 [Medium] 找出每个客户名下最贵的VPN月租费。

**判定**: ✅正确
**原因**: 完全匹配
**表选择**: 生成=t_l3vpn_service | 期望=t_l3vpn_service
**列选择**: 生成=customer_id, customer_name, max_monthly_fee | 期望=customer_id, customer_name, max_monthly_fee
**行数**: 生成=30 | 期望=30
**隐性知识**: 最贵业务按 monthly_fee 聚合到客户维度

---

### Q78 [Medium] 查询所有同时启用组播和加密的VPN业务。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多1行, 缺少1行
**表选择**: 生成=t_l3vpn_service | 期望=t_l3vpn_service
**列选择**: 生成=vpn_id, vpn_name, customer_name | 期望=vpn_id, vpn_name, customer_name, service_level
**行数**: 生成=1 | 期望=1
**隐性知识**: 双特性业务→multicast_enabled=TRUE AND encryption_enabled=TRUE
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT s.vpn_id, s.vpn_name, s.customer_name FROM t_l3vpn_service s WHERE s.multicast_enabled AND s.encryption_enabled

-- 期望SQL:
SELECT vpn_id, vpn_name, customer_name, service_level
FROM t_l3vpn_service
WHERE multicast_enabled = TRUE AND encryption_enabled = TRUE
ORDER BY customer_name, vpn_name;
```

---

### Q79 [Medium] 查询所有保护类型为HOT_STANDBY且运行状态为UP的隧道。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多18行, 缺少18行
**表选择**: 生成=t_tunnel | 期望=t_tunnel
**列选择**: 生成=tunnel_id, tunnel_name, protection_type, oper_status | 期望=tunnel_id, tunnel_name, source_ne_id, dest_ne_id, protection_type
**行数**: 生成=18 | 期望=18
**隐性知识**: 保护类型取自 t_tunnel.protection_type；运行状态看隧道基础表 oper_status
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT t.tunnel_id, t.tunnel_name, t.protection_type, t.oper_status FROM t_tunnel t WHERE t.protection_type = 'HOT_STANDBY' AND t.oper_status = 'UP'

-- 期望SQL:
SELECT tunnel_id, tunnel_name, source_ne_id, dest_ne_id, protection_type
FROM t_tunnel
WHERE protection_type = 'HOT_STANDBY' AND oper_status = 'UP'
ORDER BY tunnel_name;
```

---

### Q80 [Medium] 统计每台设备最近24小时的平均功耗。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多50行, 缺少50行
**表选择**: 生成=t_ne_perf_kpi | 期望=t_ne_perf_kpi, t_network_element
**列选择**: 生成=ne_id, avg_power_w | 期望=ne_name, avg_power_w
**行数**: 生成=50 | 期望=50
**隐性知识**: 设备功耗观测值在 t_ne_perf_kpi.power_consumption_w；按设备和24小时窗口聚合
**知识缺口**: 返回列不同, JOIN路径错误

**SQL对比**:

```sql
-- 生成SQL:
SELECT k.ne_id, AVG(k.power_consumption_w) AS avg_power_w FROM t_ne_perf_kpi k WHERE k.collect_time >= NOW() - INTERVAL 24 HOUR GROUP BY k.ne_id

-- 期望SQL:
SELECT ne.ne_name, ROUND(AVG(k.power_consumption_w), 2) AS avg_power_w
FROM t_ne_perf_kpi k
JOIN t_network_element ne ON k.ne_id = ne.ne_id
WHERE k.collect_time >= NOW() - INTERVAL '24 hours'
GROUP BY ne.ne_name
ORDER BY avg_power_w DESC, ne.ne_name;
```

---

### Q81 [Hard] 查询最近7天每条隧道的SLA违规率，并找出超过10%的隧道。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多40行, 缺少40行
**表选择**: 生成=t_tunnel, t_tunnel_perf_kpi | 期望=t_tunnel, t_tunnel_perf_kpi
**列选择**: 生成=tunnel_id, tunnel_name, violation_rate_pct | 期望=tunnel_name, tunnel_sla_violation_rate_pct
**行数**: 生成=40 | 期望=40
**隐性知识**: 隧道SLA违规率= sla_violation=TRUE 样本数 / 总样本数；并非业务层 VPN SLA
**知识缺口**: 返回列不同, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT t.tunnel_id, t.tunnel_name, COUNT(*) FILTER (WHERE k.sla_violation) * 100.0 / COUNT(*) AS violation_rate_pct FROM t_tunnel_perf_kpi k JOIN t_tunnel t ON k.tunnel_id = t.tunnel_id WHERE k.collect_time >= NOW() - INTERVAL 7 DAY GROUP BY t.tunnel_id, t.tunnel_name HAVING COUNT(*) FILTER (WHERE k.sla_violation) * 100.0 / COUNT(*) > 10

-- 期望SQL:
SELECT t.tunnel_name,
       ROUND(AVG(CASE WHEN k.sla_violation THEN 1.0 ELSE 0.0 END) * 100, 2) AS tunnel_sla_violation_rate_pct
FROM t_tunnel_perf_kpi k
JOIN t_tunnel t ON k.tunnel_id = t.tunnel_id
WHERE k.collect_time >= NOW() - INTERVAL '7 days'
GROUP BY t.tunnel_name
HAVING AVG(CASE WHEN k.sla_violation THEN 1.0 ELSE 0.0 END) > 0.10
ORDER BY tunnel_sla_violation_rate_pct DESC, t.tunnel_name;
```

---

### Q82 [Hard] 找出所有VPN中同一客户跨区域部署的业务。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多21行, 缺少21行
**表选择**: 生成=t_l3vpn_service, t_network_element, t_site, t_vpn_pe_binding | 期望=t_l3vpn_service, t_network_element, t_site, t_vpn_pe_binding
**列选择**: 生成=vpn_id, vpn_name, customer_id, customer_name | 期望=vpn_id, vpn_name, customer_name, region_count
**行数**: 生成=21 | 期望=21
**隐性知识**: 跨区域业务=同一 VPN 通过绑定的PE所在站点覆盖多个不同 region
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT s.vpn_id, s.vpn_name, s.customer_id, s.customer_name FROM t_l3vpn_service s JOIN t_vpn_pe_binding b ON s.vpn_id = b.vpn_id JOIN t_network_element n ON b.ne_id = n.ne_id JOIN t_site st ON n.site_id = st.site_id GROUP BY s.vpn_id, s.vpn_name, s.customer_id, s.customer_name HAVING COUNT(DISTINCT st.region) > 1

-- 期望SQL:
WITH vpn_region AS (
  SELECT DISTINCT v.vpn_id, v.vpn_name, v.customer_name, s.region
  FROM t_l3vpn_service v
  JOIN t_vpn_pe_binding b ON v.vpn_id = b.vpn_id
  JOIN t_network_element ne ON b.ne_id = ne.ne_id
  JOIN t_site s ON ne.site_id = s.site_id
)
SELECT vpn_id, vpn_name, customer_name, COUNT(DISTINCT region) AS region_count
FROM vpn_region
GROUP BY vpn_id, vpn_name, customer_name
HAVING COUNT(DISTINCT region) > 1
ORDER BY region_count DESC, customer_name, vpn_name;
```

---

### Q83 [Hard] 查询那些绑定了VRF但VRF当前路由数为0的VPN接入记录。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_vpn_pe_binding, t_vrf_instance | 期望=t_l3vpn_service, t_vpn_pe_binding, t_vrf_instance
**列选择**: 生成=binding_id, vpn_id, ne_id, vrf_id, vrf_name, current_route_count | 期望=binding_id, vpn_name, vrf_name, current_route_count
**行数**: 生成=0 | 期望=0
**隐性知识**: 配置存在但无路由：binding.vrf_id 关联的 VRF current_route_count=0
**知识缺口**: 返回列不同, JOIN路径错误

**SQL对比**:

```sql
-- 生成SQL:
SELECT b.binding_id, b.vpn_id, b.ne_id, b.vrf_id, v.vrf_name, v.current_route_count FROM t_vpn_pe_binding b JOIN t_vrf_instance v ON b.vrf_id = v.vrf_id WHERE v.current_route_count = 0

-- 期望SQL:
SELECT b.binding_id, v.vpn_name, vr.vrf_name, vr.current_route_count
FROM t_vpn_pe_binding b
JOIN t_l3vpn_service v ON b.vpn_id = v.vpn_id
JOIN t_vrf_instance vr ON b.vrf_id = vr.vrf_id
WHERE vr.current_route_count = 0
ORDER BY b.binding_id;
```

---

### Q84 [Hard] 找出每个客户最近30天平均MOS最低的VPN。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多30行, 缺少30行
**表选择**: 生成=t_l3vpn_service, t_vpn_sla_kpi | 期望=t_l3vpn_service, t_vpn_sla_kpi
**列选择**: 生成=customer_id, customer_name, vpn_id, vpn_name, avg_mos | 期望=customer_id, customer_name, vpn_id, vpn_name, avg_mos
**行数**: 生成=30 | 期望=30
**隐性知识**: MOS仅在业务SLA KPI表；每客户内取平均MOS最低的VPN
**知识缺口**: 业务规则缺失

**SQL对比**:

```sql
-- 生成SQL:
SELECT customer_id, customer_name, vpn_id, vpn_name, avg_mos FROM (SELECT s.customer_id, s.customer_name, s.vpn_id, s.vpn_name, AVG(k.mos_score) AS avg_mos, ROW_NUMBER() OVER (PARTITION BY s.customer_id ORDER BY AVG(k.mos_score) ASC) AS rn FROM t_l3vpn_service s JOIN t_vpn_sla_kpi k ON s.vpn_id = k.vpn_id WHERE k.collect_time >= NOW() - INTERVAL 30 DAY GROUP BY s.customer_id, s.customer_name, s.vpn_id, s.vpn_name) t WHERE t.rn = 1

-- 期望SQL:
WITH vpn_mos AS (
  SELECT v.customer_id, v.customer_name, v.vpn_id, v.vpn_name, AVG(s.mos_score) AS avg_mos
  FROM t_vpn_sla_kpi s
  JOIN t_l3vpn_service v ON s.vpn_id = v.vpn_id
  WHERE s.collect_time >= NOW() - INTERVAL '30 days'
  GROUP BY v.customer_id, v.customer_name, v.vpn_id, v.vpn_name
), ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY avg_mos ASC NULLS LAST, vpn_id) AS rn
  FROM vpn_mos
)
SELECT customer_id, customer_name, vpn_id, vpn_name, ROUND(avg_mos, ...
```

---

### Q85 [Hard] 统计每个PE设备承载的ACTIVE VPN总带宽。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多20行, 缺少20行
**表选择**: 生成=t_l3vpn_service, t_network_element, t_vpn_pe_binding | 期望=t_l3vpn_service, t_network_element, t_vpn_pe_binding
**列选择**: 生成=ne_id, ne_name, total_bandwidth_mbps | 期望=ne_name, total_vpn_bandwidth_mbps
**行数**: 生成=20 | 期望=20
**隐性知识**: 承载VPN总带宽要通过绑定表把 PE 与 VPN 关联，再汇总 VPN.bandwidth_mbps
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT b.ne_id, n.ne_name, SUM(s.bandwidth_mbps) AS total_bandwidth_mbps FROM t_vpn_pe_binding b JOIN t_l3vpn_service s ON b.vpn_id = s.vpn_id JOIN t_network_element n ON b.ne_id = n.ne_id WHERE s.admin_status = 'ACTIVE' GROUP BY b.ne_id, n.ne_name

-- 期望SQL:
SELECT ne.ne_name, SUM(v.bandwidth_mbps) AS total_vpn_bandwidth_mbps
FROM t_vpn_pe_binding b
JOIN t_l3vpn_service v ON b.vpn_id = v.vpn_id
JOIN t_network_element ne ON b.ne_id = ne.ne_id
WHERE v.admin_status = 'ACTIVE'
GROUP BY ne.ne_name
ORDER BY total_vpn_bandwidth_mbps DESC NULLS LAST, ne.ne_name;
```

---

### Q86 [Hard] 找出最近7天接口错误包总数最高的前10台设备。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多10行, 缺少10行
**表选择**: 生成=t_interface_perf_kpi, t_network_element | 期望=t_interface_perf_kpi, t_network_element
**列选择**: 生成=ne_id, ne_name, total_errors | 期望=ne_name, total_error_packets
**行数**: 生成=10 | 期望=10
**隐性知识**: 接口错误包总数=in_error_packets + out_error_packets；按设备聚合后排序
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT k.ne_id, n.ne_name, SUM(k.in_error_packets + k.out_error_packets) AS total_errors FROM t_interface_perf_kpi k JOIN t_network_element n ON k.ne_id = n.ne_id WHERE k.collect_time >= NOW() - INTERVAL 7 DAY GROUP BY k.ne_id, n.ne_name ORDER BY total_errors DESC LIMIT 10

-- 期望SQL:
SELECT ne.ne_name,
       SUM(k.in_error_packets + k.out_error_packets) AS total_error_packets
FROM t_interface_perf_kpi k
JOIN t_network_element ne ON k.ne_id = ne.ne_id
WHERE k.collect_time >= NOW() - INTERVAL '7 days'
GROUP BY ne.ne_name
ORDER BY total_error_packets DESC, ne.ne_name
LIMIT 10;
```

---

### Q87 [Hard] 查询没有任何Tunnel承载的SRv6 Policy。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多26行, 缺少26行
**表选择**: 生成=t_srv6_policy, t_tunnel | 期望=t_srv6_policy, t_tunnel
**列选择**: 生成=policy_id, policy_name | 期望=policy_id, policy_name, source_ne_id, dest_ne_id
**行数**: 生成=26 | 期望=26
**隐性知识**: 空闲策略=在 t_tunnel 中不存在 policy_id 关联记录；策略是否被隧道使用是反向关系
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT p.policy_id, p.policy_name FROM t_srv6_policy p LEFT JOIN t_tunnel t ON p.policy_id = t.policy_id WHERE t.tunnel_id IS NULL

-- 期望SQL:
SELECT sp.policy_id, sp.policy_name, sp.source_ne_id, sp.dest_ne_id
FROM t_srv6_policy sp
WHERE NOT EXISTS (
  SELECT 1 FROM t_tunnel t WHERE t.policy_id = sp.policy_id
)
ORDER BY sp.policy_name;
```

---

### Q88 [Hard] 查询最近24小时每个区域的平均接口丢弃包数。

**判定**: ⚠️错误
**原因**: 值不同: 1行匹配, 生成多4行, 缺少4行
**表选择**: 生成=t_interface_perf_kpi, t_network_element, t_site | 期望=t_interface_perf_kpi, t_network_element, t_site
**列选择**: 生成=region, avg_discard_packets | 期望=region, avg_discard_packets
**行数**: 生成=5 | 期望=5
**隐性知识**: 丢弃包数=in_discard_packets + out_discard_packets；区域通过接口KPI→设备→站点
**知识缺口**: 业务规则缺失

**SQL对比**:

```sql
-- 生成SQL:
SELECT st.region, AVG(k.in_discard_packets + k.out_discard_packets) AS avg_discard_packets FROM t_interface_perf_kpi k JOIN t_network_element n ON k.ne_id = n.ne_id JOIN t_site st ON n.site_id = st.site_id WHERE k.collect_time >= NOW() - INTERVAL 24 HOUR GROUP BY st.region

-- 期望SQL:
SELECT s.region,
       ROUND(AVG(k.in_discard_packets + k.out_discard_packets), 2) AS avg_discard_packets
FROM t_interface_perf_kpi k
JOIN t_network_element ne ON k.ne_id = ne.ne_id
JOIN t_site s ON ne.site_id = s.site_id
WHERE k.collect_time >= NOW() - INTERVAL '24 hours'
GROUP BY s.region
ORDER BY avg_discard_packets DESC, s.region;
```

---

### Q89 [Hard] 找出站点等级为TIER1且拥有至少2台PE的城市。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多1行, 缺少1行
**表选择**: 生成=t_network_element, t_site | 期望=t_network_element, t_site
**列选择**: 生成=city | 期望=city, pe_count
**行数**: 生成=1 | 期望=1
**隐性知识**: 核心站点城市定义为 site.tier=TIER1 且该站点内 PE 数>=2；输出城市维度去重
**知识缺口**: 返回列不同, 业务规则缺失

**SQL对比**:

```sql
-- 生成SQL:
SELECT st.city FROM t_site st JOIN t_network_element n ON st.site_id = n.site_id WHERE st.tier = 'TIER1' AND n.role = 'PE' GROUP BY st.city HAVING COUNT(DISTINCT n.ne_id) >= 2

-- 期望SQL:
SELECT s.city, COUNT(DISTINCT ne.ne_id) AS pe_count
FROM t_site s
JOIN t_network_element ne ON s.site_id = ne.site_id
WHERE s.tier = 'TIER1' AND ne.role = 'PE'
GROUP BY s.city
HAVING COUNT(DISTINCT ne.ne_id) >= 2
ORDER BY pe_count DESC, s.city;
```

---

### Q90 [Hard] 查询最近7天每个客户的平均时延和平均抖动，并仅保留GOLD/PLATINUM客户。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多12行, 缺少12行
**表选择**: 生成=t_l3vpn_service, t_vpn_sla_kpi | 期望=t_l3vpn_service, t_vpn_sla_kpi
**列选择**: 生成=customer_id, customer_name, avg_latency_ms, avg_jitter_ms | 期望=customer_id, customer_name, avg_latency_ms, avg_jitter_ms
**行数**: 生成=12 | 期望=12
**隐性知识**: 客户性能画像来自 VPN SLA KPI；只保留 service_level 高等级业务
**知识缺口**: 业务规则缺失

**SQL对比**:

```sql
-- 生成SQL:
SELECT s.customer_id, s.customer_name, AVG(k.e2e_latency_avg_ms) AS avg_latency_ms, AVG(k.e2e_jitter_avg_ms) AS avg_jitter_ms FROM t_l3vpn_service s JOIN t_vpn_sla_kpi k ON s.vpn_id = k.vpn_id WHERE k.collect_time >= NOW() - INTERVAL 7 DAY AND s.service_level IN ('GOLD', 'PLATINUM') GROUP BY s.customer_id, s.customer_name

-- 期望SQL:
SELECT v.customer_id, v.customer_name,
       ROUND(AVG(s.e2e_latency_avg_ms), 2) AS avg_latency_ms,
       ROUND(AVG(s.e2e_jitter_avg_ms), 2) AS avg_jitter_ms
FROM t_vpn_sla_kpi s
JOIN t_l3vpn_service v ON s.vpn_id = v.vpn_id
WHERE v.service_level IN ('GOLD', 'PLATINUM')
  AND s.collect_time >= NOW() - INTERVAL '7 days'
GROUP BY v.customer_id, v.customer_name
ORDER BY avg_latency_ms DESC, avg_jitter_ms DESC, v.customer_name;
```

---

### Q91 [Extra Hard] 找出最近30天内至少出现过3次SLA状态切换（达标/不达标变化）的VPN。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多28行, 缺少28行
**表选择**: 生成=t_vpn_sla_kpi | 期望=t_l3vpn_service, t_vpn_sla_kpi
**列选择**: 生成=vpn_id | 期望=vpn_id, vpn_name, customer_name, switch_count
**行数**: 生成=28 | 期望=28
**隐性知识**: SLA状态切换不是现成字段，需要按时间排序比较相邻 sla_overall_met 状态变化次数
**知识缺口**: 返回列不同, JOIN路径错误, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT vpn_id FROM (SELECT k.vpn_id, k.collect_time, k.sla_overall_met, LAG(k.sla_overall_met) OVER (PARTITION BY k.vpn_id ORDER BY k.collect_time) AS prev_met FROM t_vpn_sla_kpi k WHERE k.collect_time >= NOW() - INTERVAL 30 DAY) t WHERE t.sla_overall_met IS DISTINCT FROM t.prev_met AND t.prev_met IS NOT NULL GROUP BY vpn_id HAVING COUNT(*) >= 3

-- 期望SQL:
WITH ordered AS (
  SELECT vpn_id, collect_time, sla_overall_met,
         LAG(sla_overall_met) OVER (PARTITION BY vpn_id ORDER BY collect_time) AS prev_state
  FROM t_vpn_sla_kpi
  WHERE collect_time >= NOW() - INTERVAL '30 days'
), switches AS (
  SELECT vpn_id,
         SUM(CASE WHEN prev_state IS NOT NULL AND prev_state <> sla_overall_met THEN 1 ELSE 0 END) AS switch_count
  FROM ordered
  GROUP BY vpn_id
)
SELECT v.vpn_id, v.vpn_name, v.customer_name, s.switch_count
FROM switches s
JOIN t_l...
```

---

### Q92 [Extra Hard] 找出最近7天同时满足高CPU（>80%）且高接口错误（总错误包>1000）的设备。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_interface_perf_kpi, t_ne_perf_kpi | 期望=t_interface_perf_kpi, t_ne_perf_kpi, t_network_element
**列选择**: 生成=ne_id | 期望=ne_name
**行数**: 生成=0 | 期望=0
**隐性知识**: 跨事实表复合异常：设备KPI 与 接口KPI 同时超阈值，需要分别聚合后再相交
**知识缺口**: 返回列不同, JOIN路径错误

**SQL对比**:

```sql
-- 生成SQL:
SELECT nc.ne_id FROM (SELECT k.ne_id FROM t_ne_perf_kpi k WHERE k.collect_time >= NOW() - INTERVAL 7 DAY GROUP BY k.ne_id HAVING AVG(k.cpu_usage_avg_pct) > 80) nc JOIN (SELECT k.ne_id FROM t_interface_perf_kpi k WHERE k.collect_time >= NOW() - INTERVAL 7 DAY GROUP BY k.ne_id HAVING SUM(k.in_error_packets + k.out_error_packets) > 1000) ic ON nc.ne_id = ic.ne_id

-- 期望SQL:
WITH cpu_hot AS (
  SELECT ne_id
  FROM t_ne_perf_kpi
  WHERE collect_time >= NOW() - INTERVAL '7 days'
  GROUP BY ne_id
  HAVING AVG(cpu_usage_avg_pct) > 80
), if_error_hot AS (
  SELECT ne_id
  FROM t_interface_perf_kpi
  WHERE collect_time >= NOW() - INTERVAL '7 days'
  GROUP BY ne_id
  HAVING SUM(in_error_packets + out_error_packets) > 1000
)
SELECT ne.ne_name
FROM t_network_element ne
JOIN cpu_hot c ON ne.ne_id = c.ne_id
JOIN if_error_hot e ON ne.ne_id = e.ne_id
ORDER BY ne.ne_name;
```

---

### Q93 [Extra Hard] 找出那些最新时延不达标、且其底层承载类型为SRV6_TE的GOLD VPN业务。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_l3vpn_service, t_vpn_sla_kpi | 期望=t_l3vpn_service, t_vpn_sla_kpi
**列选择**: 生成=vpn_id, vpn_name, customer_name | 期望=vpn_name, customer_name, e2e_latency_avg_ms, max_latency_ms
**行数**: 生成=0 | 期望=0
**隐性知识**: 业务筛选=GOLD + underlay_type=SRV6_TE；最新时延不达标看 sla_latency_met=FALSE 的最新样本
**知识缺口**: 返回列不同, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT s.vpn_id, s.vpn_name, s.customer_name FROM t_l3vpn_service s WHERE s.service_level = 'GOLD' AND s.underlay_type = 'SRV6_TE' AND s.vpn_id IN (SELECT k.vpn_id FROM t_vpn_sla_kpi k WHERE k.collect_time = (SELECT MAX(k2.collect_time) FROM t_vpn_sla_kpi k2 WHERE k2.vpn_id = k.vpn_id) AND NOT k.sla_latency_met)

-- 期望SQL:
WITH latest AS (
  SELECT vpn_id, MAX(collect_time) AS max_time
  FROM t_vpn_sla_kpi
  GROUP BY vpn_id
)
SELECT v.vpn_name, v.customer_name, s.e2e_latency_avg_ms, v.max_latency_ms
FROM latest l
JOIN t_vpn_sla_kpi s ON l.vpn_id = s.vpn_id AND l.max_time = s.collect_time
JOIN t_l3vpn_service v ON s.vpn_id = v.vpn_id
WHERE v.service_level = 'GOLD'
  AND v.underlay_type = 'SRV6_TE'
  AND s.sla_latency_met = FALSE
ORDER BY s.e2e_latency_avg_ms DESC, v.vpn_name;
```

---

### Q94 [Extra Hard] 统计每条SRv6 Policy最近7天关联隧道的平均实测时延，并找出超过Policy约束的策略。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_srv6_policy, t_tunnel, t_tunnel_perf_kpi | 期望=t_srv6_policy, t_tunnel
**列选择**: 生成=policy_id, policy_name, policy_max_latency, avg_latency_ms | 期望=policy_id, policy_name, avg_measured_latency_ms, max_latency_ms
**行数**: 生成=0 | 期望=0
**隐性知识**: Policy约束与 Tunnel 实测对比：通过 t_tunnel.policy_id 关联，再比较 AVG(measured_latency_ms) 与 sp.max_latency_ms
**知识缺口**: 返回列不同, JOIN路径错误

**SQL对比**:

```sql
-- 生成SQL:
SELECT p.policy_id, p.policy_name, p.max_latency_ms AS policy_max_latency, avg_lat.avg_latency_ms FROM t_srv6_policy p JOIN (SELECT t.policy_id, AVG(k.latency_avg_ms) AS avg_latency_ms FROM t_tunnel t JOIN t_tunnel_perf_kpi k ON t.tunnel_id = k.tunnel_id WHERE k.collect_time >= NOW() - INTERVAL 7 DAY AND t.policy_id IS NOT NULL GROUP BY t.policy_id) avg_lat ON p.policy_id = avg_lat.policy_id WHERE avg_lat.avg_latency_ms > p.max_latency_ms

-- 期望SQL:
SELECT sp.policy_id, sp.policy_name,
       ROUND(AVG(t.measured_latency_ms), 2) AS avg_measured_latency_ms,
       sp.max_latency_ms
FROM t_srv6_policy sp
JOIN t_tunnel t ON sp.policy_id = t.policy_id
WHERE t.created_at >= NOW() - INTERVAL '7 days'
GROUP BY sp.policy_id, sp.policy_name, sp.max_latency_ms
HAVING AVG(t.measured_latency_ms) > sp.max_latency_ms
ORDER BY avg_measured_latency_ms DESC, sp.policy_name;
```

---

### Q95 [Extra Hard] 找出每个区域中合同金额最高的三个VPN客户（按客户总月租费）。

**判定**: ✅正确
**原因**: 完全匹配
**表选择**: 生成=t_l3vpn_service, t_network_element, t_site, t_vpn_pe_binding | 期望=t_l3vpn_service, t_network_element, t_site, t_vpn_pe_binding
**列选择**: 生成=region, customer_id, customer_name, total_fee | 期望=region, customer_id, customer_name, total_monthly_fee
**行数**: 生成=15 | 期望=15
**隐性知识**: 客户总月租费=客户下所有VPN monthly_fee 求和；区域通过绑定的PE站点归属推断；区域内Top3用窗口函数

---

### Q96 [Extra Hard] 找出所有同时满足以下条件的VPN：ACTIVE、合同未到期、最新综合SLA不达标、且最新MOS低于4.0。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多12行, 缺少12行
**表选择**: 生成=t_l3vpn_service, t_vpn_sla_kpi | 期望=t_l3vpn_service, t_vpn_sla_kpi
**列选择**: 生成=vpn_id, vpn_name, customer_name | 期望=vpn_id, vpn_name, customer_name, mos_score, sla_overall_met, contract_end_date
**行数**: 生成=12 | 期望=12
**隐性知识**: 复合经营风险识别：生命周期状态 + 合同状态 + 最新SLA状态 + 体验评分阈值
**知识缺口**: 返回列不同, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT s.vpn_id, s.vpn_name, s.customer_name FROM t_l3vpn_service s WHERE s.admin_status = 'ACTIVE' AND s.contract_end_date > CURRENT_DATE AND s.vpn_id IN (SELECT k.vpn_id FROM t_vpn_sla_kpi k WHERE k.collect_time = (SELECT MAX(k2.collect_time) FROM t_vpn_sla_kpi k2 WHERE k2.vpn_id = k.vpn_id) AND NOT k.sla_overall_met AND k.mos_score < 4.0)

-- 期望SQL:
WITH latest AS (
  SELECT vpn_id, MAX(collect_time) AS max_time
  FROM t_vpn_sla_kpi
  GROUP BY vpn_id
)
SELECT v.vpn_id, v.vpn_name, v.customer_name, s.mos_score, s.sla_overall_met, v.contract_end_date
FROM latest l
JOIN t_vpn_sla_kpi s ON l.vpn_id = s.vpn_id AND l.max_time = s.collect_time
JOIN t_l3vpn_service v ON s.vpn_id = v.vpn_id
WHERE v.admin_status = 'ACTIVE'
  AND (v.contract_end_date IS NULL OR v.contract_end_date >= CURRENT_DATE)
  AND s.sla_overall_met = FALSE
  AND s.mos_score < 4....
```

---

### Q97 [Extra Hard] 找出最近30天每个客户按平均时延/保证带宽定义的效率最差VPN。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多30行, 缺少30行
**表选择**: 生成=t_l3vpn_service, t_vpn_sla_kpi | 期望=t_l3vpn_service, t_vpn_sla_kpi
**列选择**: 生成=customer_id, customer_name, vpn_id, vpn_name, efficiency | 期望=customer_id, customer_name, vpn_id, vpn_name, latency_per_mbps
**行数**: 生成=30 | 期望=30
**隐性知识**: 效率最差不是现成概念：平均时延 ÷ SLA带宽；同客户内取该比值最高的VPN
**知识缺口**: 返回列不同

**SQL对比**:

```sql
-- 生成SQL:
SELECT customer_id, customer_name, vpn_id, vpn_name, efficiency FROM (SELECT s.customer_id, s.customer_name, s.vpn_id, s.vpn_name, AVG(k.e2e_latency_avg_ms) / NULLIF(s.bandwidth_mbps, 0) AS efficiency, ROW_NUMBER() OVER (PARTITION BY s.customer_id ORDER BY AVG(k.e2e_latency_avg_ms) / NULLIF(s.bandwidth_mbps, 0) DESC) AS rn FROM t_l3vpn_service s JOIN t_vpn_sla_kpi k ON s.vpn_id = k.vpn_id WHERE k.collect_time >= NOW() - INTERVAL 30 DAY GROUP BY s.customer_id, s.customer_name, s.vpn_id, s.vpn_nam...

-- 期望SQL:
WITH vpn_eff AS (
  SELECT v.customer_id, v.customer_name, v.vpn_id, v.vpn_name,
         AVG(s.e2e_latency_avg_ms) / NULLIF(v.bandwidth_mbps, 0) AS latency_per_mbps
  FROM t_vpn_sla_kpi s
  JOIN t_l3vpn_service v ON s.vpn_id = v.vpn_id
  WHERE s.collect_time >= NOW() - INTERVAL '30 days'
    AND v.bandwidth_mbps IS NOT NULL AND v.bandwidth_mbps > 0
  GROUP BY v.customer_id, v.customer_name, v.vpn_id, v.vpn_name, v.bandwidth_mbps
), ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY custome...
```

---

### Q98 [Extra Hard] 找出最近7天路径切换后仍持续高抖动（平均抖动>10ms）的隧道。

**判定**: 🔘无法验证
**原因**: 双方均0行，无法验证语义正确性 (列不一致)
**表选择**: 生成=t_tunnel, t_tunnel_perf_kpi | 期望=t_tunnel, t_tunnel_perf_kpi
**列选择**: 生成=tunnel_id, tunnel_name, avg_jitter_ms | 期望=tunnel_name, total_path_changes, avg_jitter_ms
**行数**: 生成=0 | 期望=0
**隐性知识**: 切换后高抖动= path_change_count>0 且 7天平均 jitter_avg_ms>10；属于时序 + 质量复合条件
**知识缺口**: 返回列不同, 聚合逻辑不同, 时间窗口处理

**SQL对比**:

```sql
-- 生成SQL:
SELECT t.tunnel_id, t.tunnel_name, AVG(k.jitter_avg_ms) AS avg_jitter_ms FROM t_tunnel t JOIN t_tunnel_perf_kpi k ON t.tunnel_id = k.tunnel_id WHERE k.collect_time >= NOW() - INTERVAL 7 DAY AND t.tunnel_id IN (SELECT k2.tunnel_id FROM t_tunnel_perf_kpi k2 WHERE k2.collect_time >= NOW() - INTERVAL 7 DAY AND k2.path_change_count > 0) GROUP BY t.tunnel_id, t.tunnel_name HAVING AVG(k.jitter_avg_ms) > 10

-- 期望SQL:
SELECT t.tunnel_name,
       SUM(k.path_change_count) AS total_path_changes,
       ROUND(AVG(k.jitter_avg_ms), 2) AS avg_jitter_ms
FROM t_tunnel_perf_kpi k
JOIN t_tunnel t ON k.tunnel_id = t.tunnel_id
WHERE k.collect_time >= NOW() - INTERVAL '7 days'
GROUP BY t.tunnel_name
HAVING SUM(k.path_change_count) > 0 AND AVG(k.jitter_avg_ms) > 10
ORDER BY avg_jitter_ms DESC, total_path_changes DESC, t.tunnel_name;
```

---

### Q99 [Extra Hard] 计算每个站点的网络压力指数 = 0.4×平均CPU + 0.3×平均内存 + 0.3×平均接口出方向利用率，并输出前10名。

**判定**: ⚠️错误
**原因**: 值不同: 0行匹配, 生成多10行, 缺少10行
**表选择**: 生成=t_interface_perf_kpi, t_ne_perf_kpi, t_network_element, t_site | 期望=t_interface_perf_kpi, t_ne_perf_kpi, t_network_element, t_site
**列选择**: 生成=site_id, site_name, pressure_index | 期望=site_name, pressure_index
**行数**: 生成=10 | 期望=10
**隐性知识**: 网络压力指数是跨事实表的自定义复合指标：设备KPI + 接口KPI，并在站点维度汇总
**知识缺口**: 返回列不同, 枚举值/条件缺失, 时间窗口处理, 业务规则缺失

**SQL对比**:

```sql
-- 生成SQL:
SELECT st.site_id, st.site_name, 0.4 * AVG(nk.cpu_usage_avg_pct) + 0.3 * AVG(nk.memory_usage_avg_pct) + 0.3 * AVG(ik.out_bandwidth_usage_pct) AS pressure_index FROM t_site st JOIN t_network_element n ON st.site_id = n.site_id JOIN t_ne_perf_kpi nk ON n.ne_id = nk.ne_id JOIN t_interface_perf_kpi ik ON n.ne_id = ik.ne_id GROUP BY st.site_id, st.site_name ORDER BY pressure_index DESC LIMIT 10

-- 期望SQL:
WITH ne_site AS (
  SELECT ne_id, site_id FROM t_network_element
), ne_metrics AS (
  SELECT n.site_id,
         AVG(k.cpu_usage_avg_pct) AS avg_cpu,
         AVG(k.memory_usage_avg_pct) AS avg_mem
  FROM t_ne_perf_kpi k
  JOIN ne_site n ON k.ne_id = n.ne_id
  WHERE k.collect_time >= NOW() - INTERVAL '7 days'
  GROUP BY n.site_id
), if_metrics AS (
  SELECT ne.site_id,
         AVG(k.out_bandwidth_usage_pct) AS avg_out_bw
  FROM t_interface_perf_kpi k
  JOIN t_network_element ne ON k.ne_id = ne....
```

---

### Q100 [Extra Hard] 找出最近30天高价值高风险客户：PLATINUM/GOLD业务月租费总和排名前20%，且SLA达标率低于95%。

**判定**: ⚠️错误
**原因**: 行数不同: 生成3行 vs 期望6行
**表选择**: 生成=t_l3vpn_service, t_vpn_sla_kpi | 期望=t_l3vpn_service, t_vpn_sla_kpi
**列选择**: 生成=customer_id, customer_name, total_fee, sla_met_rate | 期望=customer_id, customer_name, premium_monthly_fee, sla_hit_rate_pct
**行数**: 生成=3 | 期望=6
**隐性知识**: 高价值高风险是组合经营概念：高价值=高等级业务月租费位于客户前20%；高风险=SLA达标率<95%
**知识缺口**: 返回列不同, 聚合逻辑不同

**SQL对比**:

```sql
-- 生成SQL:
WITH customer_stats AS (SELECT s.customer_id, s.customer_name, SUM(s.monthly_fee) AS total_fee, COUNT(*) FILTER (WHERE k.sla_overall_met) * 100.0 / COUNT(*) AS sla_met_rate FROM t_l3vpn_service s JOIN t_vpn_sla_kpi k ON s.vpn_id = k.vpn_id WHERE s.service_level IN ('PLATINUM', 'GOLD') AND k.collect_time >= NOW() - INTERVAL 30 DAY GROUP BY s.customer_id, s.customer_name), ranked AS (SELECT *, PERCENT_RANK() OVER (ORDER BY total_fee ASC) AS fee_pct FROM customer_stats) SELECT customer_id, customer...

-- 期望SQL:
WITH customer_value AS (
  SELECT v.customer_id, v.customer_name,
         SUM(CASE WHEN v.service_level IN ('PLATINUM', 'GOLD') THEN v.monthly_fee ELSE 0 END) AS premium_monthly_fee
  FROM t_l3vpn_service v
  GROUP BY v.customer_id, v.customer_name
), customer_sla AS (
  SELECT v.customer_id,
         AVG(CASE WHEN s.sla_overall_met THEN 1.0 ELSE 0.0 END) AS hit_rate
  FROM t_vpn_sla_kpi s
  JOIN t_l3vpn_service v ON s.vpn_id = v.vpn_id
  WHERE s.collect_time >= NOW() - INTERVAL '30 days'
  GRO...
```

---

## 四、错误模式统计

### 4.1 知识缺口分类统计

| 缺口类型 | 出现次数 | 占错误题比例 |
|----------|----------|-------------|
| 返回列不同 | 83 | 91% |
| 聚合逻辑不同 | 20 | 22% |
| JOIN路径错误 | 19 | 21% |
| 枚举值/条件缺失 | 12 | 13% |
| 业务规则缺失 | 9 | 10% |
| 时间窗口处理 | 5 | 5% |
| SQL方言问题 | 1 | 1% |

> 注：一题可能同时属于多个缺口类型，因此总数可能超过错误题数(91题)。

### 4.2 缺口分布图（文本柱状图）

```
返回列不同        | ████████████████████████████████████████ 83
聚合逻辑不同       | █████████ 20
JOIN路径错误     | █████████ 19
枚举值/条件缺失     | █████ 12
业务规则缺失       | ████ 9
时间窗口处理       | ██ 5
SQL方言问题      |  1
```

### 4.3 按难度 x 缺口类型交叉统计

| 难度 | 返回列不同 | 聚合逻辑不同 | JOIN路径错误 | 枚举值/条件缺失 | 业务规则缺失 | 时间窗口处理 | SQL方言问题 |
|------|------|------|------|------|------|------|------|
| Easy | 9 | 0 | 2 | 1 | 0 | 0 | 0 |
| Medium | 25 | 4 | 7 | 3 | 1 | 0 | 1 |
| Hard | 28 | 7 | 5 | 3 | 5 | 1 | 0 |
| Extra Hard | 21 | 9 | 5 | 5 | 3 | 4 | 0 |

## 五、关键发现与建议

### 5.1 核心发现

1. **"返回列不同"是首要问题**（83题涉及）：LLM在Schema中能看到列定义和中文注释，但缺乏"业务概念→应返回哪些列"的映射知识。例如"查询设备信息"时，LLM不知道业务上期望返回`ne_id`还是只返回`ne_name`、`model`等。

2. **可执行率极高（99/100 (99%)）**：说明LLM对DuckDB SQL语法掌握良好，Schema理解基本到位。问题不在SQL生成能力，而在业务语义理解。

3. **纯列选择错误占比大**：在67题错误中，有相当部分仅因返回列不一致而判错（行数相同但列集不同），说明如果补充"业务视图定义"（即每种查询场景应返回哪些列），准确率可大幅提升。

4. **无法验证（23/100 (23%)）问题**：23题双方均返回0行，通常是时间窗口过滤导致（如"近24小时告警"在测试数据中无匹配记录）。这不代表SQL一定错误，但也无法证明正确。

5. **模型能力 vs 知识瓶颈**：Opus 4.6 的SQL生成能力本身非常强（99%可执行），但严格准确率仅9%。差距完全来自业务知识缺失，而非模型推理能力不足。这意味着**换更强的模型收益有限，补充业务知识才是关键**。

### 5.2 最高ROI的知识补充建议

按预期收益排序：

| 优先级 | 知识类型 | 预计可修复题数 | 实施方式 |
|--------|----------|---------------|----------|
| P0 | 业务视图定义（查询场景→返回列映射） | ~83题 | 在Schema中添加"查设备信息应返回ne_id, ne_name, model, ..."的注释 |
| P1 | 业务术语→枚举值映射 | ~12题 | 构建术语词典，如"华为→HUAWEI"、"在用→ACTIVE" |
| P2 | 标准JOIN路径模板 | ~19题 | 为常见多表查询提供JOIN路径示例 |
| P3 | 聚合与计算公式库 | ~20题 | 定义"利用率=used/total"等业务公式 |
| P4 | 时间窗口规范 | ~5题 | 明确"近7天"等时间表达的DuckDB写法 |
| P5 | 领域业务规则 | ~9题 | 补充网络运维领域的专业判断逻辑 |

### 5.3 推荐下一步

1. **构建"语义层"（Semantic Layer）**：在DDL Schema之上增加业务视图定义和术语映射，这是WrenAI MDL的核心价值所在。当前实验仅使用了压缩DDL，未利用MDL中的语义描述能力。

2. **Few-shot 示例注入**：针对高频错误模式（返回列、枚举值），在Prompt中加入2-3个典型示例，预计可提升10-20个百分点。

3. **Implicit Knowledge → Explicit Rules**：将100题的`implicit_knowledge`字段整理为结构化规则库，作为Prompt的一部分注入，测量天花板准确率。

4. **评测指标优化**：当前"严格匹配"过于严格（列别名不同即判错），建议增加"宽松匹配"指标（忽略列名、只比值），更真实反映语义准确性。

5. **分层实验设计**：
   - Exp1: DDL + 术语词典 → 测量枚举值/条件修复效果
   - Exp2: DDL + 术语词典 + 业务视图定义 → 测量列选择修复效果
   - Exp3: DDL + 完整语义层 + Few-shot → 测量综合效果上限
