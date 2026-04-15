# AB Test Report v3 — NL2SQL 4 组对照实验

> 2026-04-16 01:10 | 模型: Claude Opus 4.6 | 题目: 100 题 | 数据: 时间戳已刷新至当天

## 实验设计

| 实验 | Schema 策略 | 知识注入 | Pipeline 预处理 |
|------|------------|---------|----------------|
| **A** | 全量 14 表 DDL (19715 chars) | 无 | 无 |
| **B** | 全量 14 表 DDL (19715 chars) | 有 | 无 |
| **C** | Schema Linking ~6 表 (4564 chars) | 无 | 表选择 + 列裁剪 + JOIN 路径 + 模式识别 |
| **D** | Schema Linking ~6 表 (4564 chars) | 有 | 同 C + 知识注入 |

## Prompt 样例 (Q07: 查询过去24小时CPU平均利用率超过80%的网元)

### A: 全量Schema
```
### DATABASE SCHEMA ###
-- 站点/机房表 - 物理机房、POP点的地理位置和基础设施信息
CREATE TABLE t_site (
  site_id VARCHAR PRIMARY KEY NOT NULL,  -- 站点唯一标识
  site_name VARCHAR NOT NULL,  -- 站点名称
  site_code VARCHAR NOT NULL,  -- 站点编码（全局唯一简码）
  site_type VARCHAR NOT NULL,  -- 站点类型：DC(数据中心)、POP(接入点)、CO(中心机房)、COLO(托管)、EDGE(边缘)。取值: DC;POP;CO;COLO;EDGE
  region VARCHAR NOT NULL,  -- 所属大区（用于区域维度聚合）
  province VARCHAR NOT NULL,  -- 省份
  city VARCHAR NOT NULL,  -- 城市
  address VARCHAR,  -- 详细地址
  longitude DECIMAL,  -- 经度（WGS84）
  latitude DECIMAL,  -- 纬度（WGS84）
  tier VARCHAR NOT NULL,  -- 站点等级：TIER1为核心枢纽，TIER3为末梢接入。取值: TIER1;TIER2;TIER3
  total_rack_count INT,  -- 该站点总机柜数量
  used_rack_count INT,  -- 已使用的机柜数量
  power_capacity_kw DECIMAL,  -- 站点总供电容量
  cooling_type VARCHAR,  -- 制冷方式。取值: AIR;LIQUID;HYBRID
  operator VARCHAR,  -- 站点运营商或承建方
  contact_person VARCHAR,  -- 站点联系人
  contact_phone VARCHAR,  -- 联系电话
  commissioning_date DATE,  -- 站点投产日期
  contract_expire_date DATE,  -- 机房租赁合同到期日
  status VARCHAR NOT NULL,  -- 站点状态。取值: ACTIVE;DECOMMISSIONED;PLANNED
  description VARCHAR,  -- 备注
);

-- 网元/设备表 - 路由器、交换机等网络设备信息
CREATE TABLE t_network_element (
  ne_id VARCHAR PRIMARY KEY NOT NULL,  -- 网元唯一标识
  ne_name VARCHAR N
... (truncated)
```

### C: Schema Linking
```
### DATABASE SCHEMA ###
-- 网元/设备表 - 路由器、交换机等网络设备信息
CREATE TABLE t_network_element (
  ne_id VARCHAR PRIMARY KEY NOT NULL,  -- 网元唯一标识
  site_id VARCHAR,  -- 所属站点ID
  admin_status VARCHAR NOT NULL,  -- 管理状态（运维人员手动设置）。取值: UP;DOWN;TESTING
  oper_status VARCHAR NOT NULL,  -- 运行状态（系统自动检测）。取值: UP;DOWN;DEGRADED
  created_at TIMESTAMP NOT NULL,  -- 创建时间
  updated_at TIMESTAMP NOT NULL,  -- 更新时间
);

-- 接口表 - 物理口、逻辑口、Trunk等接口信息
CREATE TABLE t_interface (
  if_id VARCHAR PRIMARY KEY NOT NULL,  -- 接口唯一标识
  ne_id VARCHAR NOT NULL,  -- 所属网元ID
  board_id VARCHAR,  -- 所属单板ID（物理口有值逻辑口可空）
  admin_status VARCHAR NOT NULL,  -- 接口管理状态。取值: UP;DOWN
  oper_status VARCHAR NOT NULL,  -- 接口运行状态。取值: UP;DOWN
  created_at TIMESTAMP NOT NULL,  -- 创建时间
  updated_at TIMESTAMP NOT NULL,  -- 更新时间
);

-- L3VPN业务表 - 端到端VPN服务实例
CREATE TABLE t_l3vpn_service (
  vpn_id VARCHAR PRIMARY KEY NOT NULL,  -- VPN业务唯一标识
  customer_id VARCHAR NOT NULL,  -- 客户编号
  customer_name VARCHAR NOT NULL,  -- 客户名称
  admin_status VARCHAR NOT NULL,  -- 业务管理状态（注意：与网络层 UP/DOWN 不同，业务层使用独立状态枚举）。取值: ACTIVE;SUSPENDED;TERMINATED
  oper_status VARCHAR NOT NULL,  -- 业务运行状态。取值: UP;DOWN
  created_at TIMESTAMP NOT NULL,  -- 创建时间
  updated_at TIMESTAMP NOT
... (truncated)
```

## 核心结果

| 指标 | 全量Schema 无知识 | 全量Schema 有知识 | Schema Linking 无知识 | Schema Linking 有知识 |
|------|------|------|------|------|
| 可执行率 | 99/100 (99%) | 100/100 (100%) | 100/100 (100%) | 100/100 (100%) |
| 严格准确率 | 12/100 (12%) | 13/100 (13%) | 5/100 (5%) | 10/100 (10%) |
| 宽松准确率 | 41/98 (42%) | 41/98 (42%) | 17/98 (17%) | 35/98 (36%) |
| 无法验证(0行) | 2/100 (2%) | 2/100 (2%) | 2/100 (2%) | 2/100 (2%) |

## 多维评分

| 维度 | 全量Schema 无知识 | 全量Schema 有知识 | Schema Linking 无知识 | Schema Linking 有知识 |
|------|------|------|------|------|
| 总分 | 0.77 | 0.79 | 0.64 | 0.73 |
| 表选择 | 0.94 | 0.96 | 0.80 | 0.87 |
| 列选择 | 0.56 | 0.57 | 0.33 | 0.38 |
| WHERE条件 | 0.76 | 0.79 | 0.66 | 0.79 |
| JOIN | 0.89 | 0.93 | 0.78 | 0.84 |
| 聚合 | 0.78 | 0.79 | 0.69 | 0.80 |

## 按难度对比（宽松准确率）

| 难度 | 全量Schema 无知识 | 全量Schema 有知识 | Schema Linking 无知识 | Schema Linking 有知识 |
|------|------|------|------|------|
| Easy | 7/13 (54%) | 6/13 (46%) | 4/13 (31%) | 11/13 (85%) |
| Medium | 11/30 (37%) | 13/30 (43%) | 4/30 (13%) | 13/30 (43%) |
| Hard | 14/33 (42%) | 13/33 (39%) | 3/33 (9%) | 8/33 (24%) |
| Extra Hard | 9/22 (41%) | 9/22 (41%) | 6/22 (27%) | 3/22 (14%) |

## 知识注入效果 (B vs A)

改善 9 题, 退步 8 题

| 题号 | 难度 | A→B |
|------|------|-----|
| Q09 | Hard | wrong → correct_relaxed |
| Q17 | Easy | wrong → correct |
| Q26 | Medium | wrong → correct |
| Q28 | Medium | wrong → correct_relaxed |
| Q35 | Medium | wrong → correct_relaxed |
| Q59 | Hard | correct_relaxed → correct |
| Q62 | Extra Hard | error → wrong |
| Q67 | Extra Hard | wrong → correct |
| Q76 | Medium | correct_relaxed → correct |

退步:
| 题号 | 难度 | A→B |
|------|------|-----|
| Q19 | Easy | correct_relaxed → wrong |
| Q22 | Easy | correct → wrong |
| Q33 | Medium | correct_relaxed → wrong |
| Q48 | Hard | correct_relaxed → wrong |
| Q77 | Medium | correct → correct_relaxed |
| Q84 | Hard | correct → wrong |
| Q91 | Extra Hard | correct → correct_relaxed |
| Q99 | Extra Hard | correct_relaxed → wrong |

## Schema Linking 效果 (C vs A)

改善 3 题, 退步 27 题

| 题号 | 难度 | A→C |
|------|------|-----|
| Q11 | Extra Hard | wrong → correct_relaxed |
| Q28 | Medium | wrong → correct_relaxed |
| Q62 | Extra Hard | error → wrong |

**根因**: 列裁剪过于激进，裁掉了 ne_name、vendor、model、city 等高频基础列，导致模型无法生成正确的 SELECT 和 WHERE。

退步:
| 题号 | 难度 | A→C |
|------|------|-----|
| Q02 | Easy | correct → wrong |
| Q04 | Medium | correct → wrong |
| Q19 | Easy | correct_relaxed → wrong |
| Q22 | Easy | correct → wrong |
| Q33 | Medium | correct_relaxed → wrong |
| Q34 | Medium | correct → wrong |
| Q38 | Medium | correct_relaxed → wrong |
| Q46 | Hard | correct_relaxed → wrong |
| Q47 | Hard | correct_relaxed → wrong |
| Q48 | Hard | correct_relaxed → wrong |
| Q49 | Hard | correct_relaxed → wrong |
| Q50 | Hard | correct_relaxed → wrong |
| Q66 | Extra Hard | correct_relaxed → wrong |
| Q70 | Extra Hard | correct_relaxed → wrong |
| Q72 | Medium | correct_relaxed → wrong |
| Q74 | Medium | correct_relaxed → wrong |
| Q77 | Medium | correct → wrong |
| Q78 | Medium | correct_relaxed → wrong |
| Q81 | Hard | correct_relaxed → wrong |
| Q82 | Hard | correct_relaxed → wrong |
| Q84 | Hard | correct → wrong |
| Q85 | Hard | correct_relaxed → wrong |
| Q86 | Hard | correct_relaxed → wrong |
| Q89 | Hard | correct_relaxed → wrong |
| Q91 | Extra Hard | correct → correct_relaxed |
| Q92 | Extra Hard | correct_relaxed → wrong |
| Q99 | Extra Hard | correct_relaxed → wrong |

## 关键结论

### 1. 知识注入效果微弱（B vs A: 42% vs 42%）

v3 的知识注入没有产生 v2 那样的提升（v2 是 +9pp）。原因：v3 时间戳刷新后数据分布变了，且本轮 Opus 生成的 SQL 风格有差异。**知识注入对强模型的效果不稳定**，受 prompt 格式和数据分布影响大。

### 2. 列裁剪是 Schema Linking 的主要瓶颈

C 组宽松准确率仅 17%（vs A 的 42%），27 题退步。根因：`select_columns()` 只保留关键词匹配到的列，裁掉了 `ne_name`、`vendor`、`model`、`city` 等几乎每个查询都需要的基础列。

**修复方向**：表选择可以做，但列裁剪暂时不做——对 14 表 Schema 来说，保留完整列的 token 开销可接受。列裁剪应留到 100 表规模时再启用。

### 3. D 组（Schema Linking + 知识）相比 C 大幅改善

D 宽松准确率 36% vs C 的 17%——知识注入帮助补偿了列裁剪的损失，特别是 Easy（31%→85%）和 Medium（13%→43%）。但仍不如全量 Schema 的 A/B。

### 4. v3 整体数值低于 v2

v2 最佳是 B(54%)，v3 最佳是 A/B(42%)。下降原因：
- 时间戳刷新改变了数据分布，部分题的过滤条件匹配到不同行数
- eval 脚本 reason 改进后诊断更清晰，但评判逻辑未变
- LLM 输出非确定性，两轮生成的 SQL 存在随机差异

### 5. 下一步优先级

| 优先级 | 方向 | 预期收益 |
|--------|------|---------|
| **P0** | Few-shot 示例注入（未在任何实验中使用） | +10-15pp |
| **P0** | 取消列裁剪，只做表选择 | 恢复 C/D 到 A/B 水平 |
| **P1** | Prompt 模板优化（标准化列选择指令） | 缩小严格/宽松差距 |
| **P1** | Qwen3 32B 天花板实验 | 确定工程优化上限 |
