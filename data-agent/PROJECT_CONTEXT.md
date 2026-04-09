# 项目上下文（发给任何 AI 助手前先贴这个）

> 本文档供用户在不同 AI 助手间共享项目背景。复制全文发送即可。
> 最后更新: 2026-04-09

## 项目概述

我在做电信网管系统（NMS）的 NL2SQL（自然语言转SQL）研究。目标是让运维人员用中文提问，系统自动生成 SQL 查询电信网络数据。

## 当前阶段

已完成：
- 14 张电信表的语义层定义（MDL）+ Mock 数据生成
- WrenAI 开源项目的二次开发（Trace 日志界面）
- 100 道测试用例（13 Easy / 30 Medium / 34 Hard / 23 Extra Hard）
- 评测框架（支持三级判定：正确/错误/无法验证）
- Opus 零知识基线测试：可执行率 99%，可验证准确率 12%

核心发现：
- 模型 SQL 生成能力本身没问题（99% 可执行）
- 瓶颈是业务语义知识缺失——模型不知道"查设备信息"该返回哪些列、"在网设备"意味着什么过滤条件
- 91% 的错误是"返回列不同"，本质是业务概念→列映射的问题

下一步：
- 构建业务语义层（术语表、查询模式、业务规则）
- 用增量实验验证每种知识注入的 ROI
- 从 14 表 demo 扩展到 100+ 表生产规模

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 数据库 | DuckDB | 本地嵌入式，存 14 表电信 mock 数据 |
| 语义层 | WrenAI MDL (JSON) | 表/列/关系/描述定义 |
| NL2SQL 平台 | WrenAI (Docker) | 6 容器：engine + ibis + ai-service + qdrant + ui + bootstrap |
| LLM | DeepSeek / OpenAI GPT-4o / Claude | 通过 API 调用 |
| 评测 | 自建 Python 框架 | eval/eval_framework.py |
| 开发环境 | Mac + Claude Code | 第一试验田 |
| 部署环境 | Windows → Ubuntu 云 | 第二试验田，有防火墙 |

## 仓库结构

```
data-agent/
├── docs/              # 研究文档（领域分析、技术指引、测试报告）
├── eval/              # 评测体系（框架、测试用例、基线结果）
├── telecom/           # 电信语义层（MDL、数据生成、导入脚本）
├── WrenAI/            # WrenAI 源码（git submodule，有 UI 改动）
├── SETUP.md           # 部署指南
└── PROJECT_CONTEXT.md # 本文件
```

## 电信数据模型（14 表）

| 表 | 行数 | 用途 |
|---|---|---|
| t_site | 25 | 站点/机房 |
| t_network_element | 50 | 网元/设备（PE/P/RR/ASBR） |
| t_board | 150 | 单板/板卡 |
| t_interface | 512 | 接口（物理/逻辑/Trunk） |
| t_physical_link | 100 | 物理链路 |
| t_vrf_instance | 119 | VRF 实例 |
| t_l3vpn_service | 30 | L3VPN 业务 |
| t_vpn_pe_binding | 80 | VPN-PE 绑定（多对多） |
| t_srv6_policy | 50 | SRv6 TE 策略 |
| t_tunnel | 80 | 隧道 |
| t_ne_perf_kpi | 9600 | 设备性能 KPI（CPU/内存/温度） |
| t_interface_perf_kpi | 5280 | 接口性能 KPI（带宽/错包） |
| t_tunnel_perf_kpi | 3000 | 隧道性能 KPI（时延/抖动） |
| t_vpn_sla_kpi | 2010 | VPN SLA KPI（达标率/MOS） |

生产规模：100+ 表，~3500 列。当前 14 表是验证子集。

## 约束与偏好

1. **代码语言**: Python，中文注释/文档
2. **目录管理**: 不同类型文件必须分目录，废弃文件及时删除
3. **配置注释**: Docker/env 等配置文件的改动必须有注释说明
4. **生成文件**: .duckdb 等不在 git 中的文件必须在文档里写清楚生成步骤
5. **公司环境**: 有防火墙，不能用 Claude Code，只能复制粘贴问 Claude 网页版
6. **提交规范**: 每次 commit 说明改了什么、为什么改

## 关键文件路径

- 评测框架: `eval/eval_framework.py`
- 测试用例: `eval/telecom_test_cases_100.json`
- 时间戳刷新: `eval/refresh_timestamps.py`
- MDL 定义: `telecom/telecom_mdl.json`
- 数据生成: `telecom/generate_mock_data.py`
- WrenAI 导入: `telecom/scripts/update_wren_metadata.py`
- Docker 配置: `WrenAI/docker/docker-compose.yaml`（搜索 `[自定义]` 看改动）
- 部署指南: `SETUP.md`
