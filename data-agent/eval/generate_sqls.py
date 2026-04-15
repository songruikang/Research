"""
NL2SQL 生成器 v3 — 4 组 AB 实验 + 简陋版 Pipeline

Pipeline 流程 (Schema Linking 模式):
  Phase A: 工程预处理（零 LLM）
    A1. 关键词提取 + 领域同义词扩展
    A2. 表选择（关键词→表描述匹配 + FK 图扩展）
    A3. 列裁剪（只保留匹配的列 + PK/FK + 状态列）
    A4. JOIN 路径推导（从 FK 关系生成提示）
    A5. 查询模式识别（聚合/排名/趋势/对比/分布）
  Phase B: Prompt 组装
  Phase C: LLM 调用（1 次）
  Phase D: 工程后处理（sqlglot 校验）

用法: python generate_sqls.py  — 生成 4 组预处理数据供 SubAgent 使用
"""
import json, re
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MDL_PATH = PROJECT_ROOT / "telecom" / "input" / "telecom_mdl.json"
TEST_PATH = PROJECT_ROOT / "eval" / "telecom_test_cases_100.json"


# ─── MDL 加载 ───

def load_mdl():
    with open(MDL_PATH) as f:
        return json.load(f)


def mdl_to_ddl(mdl: dict, tables_filter: list[str] | None = None,
               columns_filter: dict[str, list[str]] | None = None) -> str:
    """从 MDL 生成 DDL。支持表过滤和列过滤。"""
    ddl_parts = []
    for model in mdl.get("models", []):
        table_name = model["name"]
        if tables_filter and table_name not in tables_filter:
            continue
        desc = model.get("properties", {}).get("description", "")
        columns = []
        keep_cols = columns_filter.get(table_name) if columns_filter else None
        for col in model.get("columns", []):
            if col.get("isHidden"):
                continue
            col_name = col["name"]
            # 列裁剪：保留 PK、FK、状态列、匹配列
            if keep_cols and col_name not in keep_cols:
                continue
            col_type = col["type"]
            col_desc = col.get("properties", {}).get("description", "")
            pk = " PRIMARY KEY" if col_name == model.get("primaryKey") else ""
            not_null = " NOT NULL" if col.get("notNull") else ""
            comment = f"  -- {col_desc}" if col_desc else ""
            columns.append(f"  {col_name} {col_type}{pk}{not_null},{comment}")
        cols_str = "\n".join(columns)
        table_comment = f"-- {desc}" if desc else ""
        ddl_parts.append(f"{table_comment}\nCREATE TABLE {table_name} (\n{cols_str}\n);")
    # FK 关系
    rels = mdl.get("relationships", [])
    if rels:
        rel_tables = set(tables_filter) if tables_filter else None
        fk_lines = []
        for rel in rels:
            condition = rel.get("condition", "")
            if rel_tables:
                if not any(t in condition for t in rel_tables):
                    continue
            join_type = rel.get("joinType", "")
            desc = rel.get("properties", {}).get("description", "")
            fk_lines.append(f"-- {condition}  ({join_type})  {desc}")
        if fk_lines:
            ddl_parts.append("\n-- ═══ RELATIONSHIPS ═══")
            ddl_parts.extend(fk_lines)
    return "\n\n".join(ddl_parts)


# ─── Schema Linking ───

DOMAIN_SYNONYMS = {
    "隧道": ["t_tunnel", "tunnel"],
    "时延": ["latency", "时延", "延迟"],
    "抖动": ["jitter", "抖动"],
    "丢包": ["packet_loss", "loss", "丢包"],
    "带宽": ["bandwidth", "带宽", "利用率"],
    "CPU": ["cpu_usage", "cpu"],
    "内存": ["memory_usage", "memory", "内存"],
    "温度": ["temperature", "温度"],
    "告警": ["alarm", "告警"],
    "功耗": ["power_consumption", "功耗"],
    "风扇": ["fan_speed", "风扇"],
    "站点": ["t_site", "site", "站点", "机房", "机柜"],
    "网元": ["t_network_element", "ne_", "网元", "设备"],
    "设备": ["t_network_element", "ne_", "网元", "设备"],
    "接口": ["t_interface", "interface", "接口", "端口", "物理口"],
    "端口": ["t_interface", "interface", "端口"],
    "单板": ["t_board", "board", "单板", "板卡", "线卡"],
    "板卡": ["t_board", "board", "板卡"],
    "链路": ["t_physical_link", "link", "链路", "光纤"],
    "VPN": ["t_l3vpn_service", "vpn", "业务"],
    "VRF": ["t_vrf_instance", "vrf"],
    "SRv6": ["t_srv6_policy", "srv6", "policy"],
    "SLA": ["t_vpn_sla_kpi", "sla", "达标", "违规"],
    "达标": ["sla", "达标", "t_vpn_sla_kpi"],
    "违规": ["sla", "违规", "t_vpn_sla_kpi"],
    "绑定": ["t_vpn_pe_binding", "binding", "绑定"],
    "客户": ["customer", "客户", "t_l3vpn_service"],
    "区域": ["region", "区域", "大区", "t_site"],
    "KPI": ["kpi", "perf"],
    "性能": ["kpi", "perf"],
    "健康": ["cpu", "memory", "temperature", "alarm"],
    "压力": ["cpu", "memory", "bandwidth"],
    "利用率": ["usage", "utilization", "pct"],
    "路由": ["route", "路由", "t_vrf_instance"],
    "BGP": ["bgp", "bgp_peer"],
    "MPLS": ["mpls"],
    "合同": ["contract", "合同", "到期"],
    "月租": ["monthly_fee", "月租"],
    "环比": ["lag", "环比", "变化", "对比", "增长"],
    "趋势": ["trend", "趋势", "每日", "daily"],
}


def _extract_keywords(text: str) -> set:
    """中文+英文关键词提取"""
    kw = set()
    for m in re.finditer(r'[\u4e00-\u9fff]{2,6}', text):
        kw.add(m.group())
    for m in re.finditer(r'[A-Za-z_][A-Za-z0-9_]+', text):
        kw.add(m.group().lower())
    return kw


def _expand_keywords(question: str) -> set:
    """关键词 + 领域同义词扩展 + KPI 表推断"""
    base = _extract_keywords(question)
    for m in re.finditer(r'[A-Za-z_][A-Za-z0-9_]+', question):
        base.add(m.group().lower())
    expanded = set(base)
    for term, synonyms in DOMAIN_SYNONYMS.items():
        if term in question or term.lower() in question.lower():
            expanded.update(s.lower() for s in synonyms)
    if any(w in question for w in ["CPU", "内存", "温度", "告警", "功耗", "风扇", "BGP"]):
        expanded.update(["t_ne_perf_kpi", "ne_perf", "kpi"])
    if any(w in question for w in ["带宽", "接口", "端口", "CRC", "丢弃", "错误包", "利用率"]):
        expanded.update(["t_interface_perf_kpi", "interface_perf", "kpi"])
    if any(w in question for w in ["隧道时延", "隧道抖动", "隧道SLA", "路径切换"]):
        expanded.update(["t_tunnel_perf_kpi", "tunnel_perf", "kpi"])
    if any(w in question for w in ["SLA达标", "SLA违规", "MOS", "可用率", "e2e", "达标率"]):
        expanded.update(["t_vpn_sla_kpi", "vpn_sla", "kpi"])
    return expanded


def build_schema_index(mdl: dict) -> dict:
    """构建 table→keywords 索引 + FK 图"""
    index = {}
    fk_graph = {}
    for model in mdl.get("models", []):
        name = model["name"]
        desc = model.get("properties", {}).get("description", "")
        keywords = _extract_keywords(desc)
        keywords.add(name.lower())
        for col in model.get("columns", []):
            keywords.add(col["name"].lower())
            col_desc = col.get("properties", {}).get("description", "")
            keywords.update(_extract_keywords(col_desc))
            if "取值:" in col_desc:
                for v in col_desc.split("取值:")[-1].strip().split(";"):
                    if v.strip():
                        keywords.add(v.strip().lower())
        index[name] = keywords
        fk_graph[name] = set()
    for rel in mdl.get("relationships", []):
        cond = rel.get("condition", "")
        tables_in_rel = [m["name"] for m in mdl["models"] if m["name"] in cond]
        for i, t1 in enumerate(tables_in_rel):
            for t2 in tables_in_rel[i+1:]:
                fk_graph.setdefault(t1, set()).add(t2)
                fk_graph.setdefault(t2, set()).add(t1)
    return {"index": index, "fk_graph": fk_graph}


def select_tables(question: str, schema_index: dict, top_k: int = 6) -> list[str]:
    """Phase A2: 表选择"""
    q_kw = _expand_keywords(question)
    scores = {}
    for table, t_kw in schema_index["index"].items():
        scores[table] = len(q_kw & t_kw)
    sorted_t = sorted(scores.items(), key=lambda x: -x[1])
    primary = [t for t, s in sorted_t if s > 0][:3]
    expanded = set(primary)
    for t in primary:
        for neighbor in schema_index["fk_graph"].get(t, set()):
            expanded.add(neighbor)
    result = sorted(expanded, key=lambda t: -scores.get(t, 0))[:top_k]
    return result if result else [sorted_t[0][0]] if sorted_t else []


def select_columns(question: str, tables: list[str], mdl: dict) -> dict[str, list[str]]:
    """Phase A3: 列裁剪 — 保留匹配列 + PK + FK + 状态列 + 时间列"""
    q_kw = _expand_keywords(question)
    ALWAYS_KEEP = {"admin_status", "oper_status", "created_at", "updated_at", "collect_time",
                   "ne_id", "site_id", "if_id", "board_id", "link_id", "tunnel_id",
                   "vpn_id", "vrf_id", "policy_id", "binding_id", "kpi_id",
                   "customer_id", "customer_name"}
    result = {}
    for model in mdl.get("models", []):
        if model["name"] not in tables:
            continue
        pk = model.get("primaryKey", "")
        kept = set()
        for col in model.get("columns", []):
            cn = col["name"]
            # 总是保留 PK、FK、状态列
            if cn == pk or cn in ALWAYS_KEEP:
                kept.add(cn)
                continue
            # 列名或列描述匹配问题关键词
            col_kw = _extract_keywords(col.get("properties", {}).get("description", ""))
            col_kw.add(cn.lower())
            if q_kw & col_kw:
                kept.add(cn)
        result[model["name"]] = sorted(kept)
    return result


def detect_join_paths(tables: list[str], mdl: dict) -> list[str]:
    """Phase A4: 从 FK 关系推导 JOIN 路径提示"""
    paths = []
    for rel in mdl.get("relationships", []):
        cond = rel.get("condition", "")
        involved = [t for t in tables if t in cond]
        if len(involved) >= 2:
            desc = rel.get("properties", {}).get("description", "")
            paths.append(f"JOIN: {cond}" + (f"  -- {desc}" if desc else ""))
    return paths


def detect_query_pattern(question: str) -> str | None:
    """Phase A5: 查询模式识别"""
    patterns = {
        "AGGREGATION": ["统计", "汇总", "总数", "数量", "求和", "平均"],
        "RANKING": ["排名", "前N", "前5", "前10", "前三", "最高", "最低", "最大", "最小", "Top"],
        "TREND": ["趋势", "每日", "每天", "环比", "增长", "变化", "对比上周"],
        "DISTRIBUTION": ["分布", "分桶", "空闲", "正常", "繁忙", "过载"],
        "THRESHOLD": ["超过", "低于", "大于", "小于", "超出", "不达标"],
        "EXISTENCE": ["没有", "不存在", "未启用", "未创建", "缺少"],
        "COMPOSITE": ["健康分", "压力指数", "风险", "评分"],
    }
    detected = []
    for pattern, keywords in patterns.items():
        if any(kw in question for kw in keywords):
            detected.append(pattern)
    return "+".join(detected) if detected else None


# ─── 完整 Pipeline ───

def run_pipeline(question: str, mdl: dict, schema_index: dict,
                 use_schema_linking: bool, knowledge: str | None) -> dict:
    """运行完整预处理 pipeline，返回组装好的 prompt 上下文"""
    result = {"question": question}

    if use_schema_linking:
        # Phase A2: 表选择
        tables = select_tables(question, schema_index)
        result["selected_tables"] = tables

        # Phase A3: 列裁剪
        col_filter = select_columns(question, tables, mdl)
        result["column_filter"] = {t: len(cols) for t, cols in col_filter.items()}

        # Phase A4: JOIN 路径
        join_paths = detect_join_paths(tables, mdl)
        result["join_paths"] = join_paths

        # 生成精简 DDL
        ddl = mdl_to_ddl(mdl, tables_filter=tables, columns_filter=col_filter)
    else:
        ddl = mdl_to_ddl(mdl)
        result["selected_tables"] = [m["name"] for m in mdl["models"]]

    # Phase A5: 查询模式识别
    pattern = detect_query_pattern(question)
    result["query_pattern"] = pattern

    # Phase B: Prompt 组装
    prompt_parts = [f"### DATABASE SCHEMA ###\n{ddl}"]

    if use_schema_linking and join_paths:
        prompt_parts.append("### JOIN PATHS ###\n" + "\n".join(join_paths))

    if pattern:
        prompt_parts.append(f"### QUERY PATTERN ###\n检测到的查询模式: {pattern}")

    if knowledge:
        prompt_parts.append(f"### DOMAIN KNOWLEDGE ###\n{knowledge}")

    prompt_parts.append(f"### QUESTION ###\n{question}")

    result["user_prompt"] = "\n\n".join(prompt_parts)
    result["ddl_chars"] = len(ddl)

    return result


# ─── 主流程：生成 4 组预处理数据 ───

def main():
    mdl = load_mdl()
    schema_index = build_schema_index(mdl)

    with open(TEST_PATH) as f:
        cases = json.load(f)

    configs = {
        "A": {"schema_linking": False, "knowledge": False, "name": "fullschema_no_knowledge"},
        "B": {"schema_linking": False, "knowledge": True,  "name": "fullschema_with_knowledge"},
        "C": {"schema_linking": True,  "knowledge": False, "name": "schemalink_no_knowledge"},
        "D": {"schema_linking": True,  "knowledge": True,  "name": "schemalink_with_knowledge"},
    }

    # 生成 questions_only（无 expected_sql）
    questions_only = [{k: c[k] for k in ["id", "difficulty", "question", "implicit_knowledge"]} for c in cases]
    with open(PROJECT_ROOT / "eval" / "questions_only.json", "w") as f:
        json.dump(questions_only, f, ensure_ascii=False, indent=2)

    # 为每组配置生成 per-question prompt
    for cfg_key, cfg in configs.items():
        prompts = {}
        stats = {"total_ddl_chars": 0, "avg_tables": 0}
        for c in cases:
            qid = c["id"]
            knowledge = c["implicit_knowledge"] if cfg["knowledge"] else None
            result = run_pipeline(c["question"], mdl, schema_index, cfg["schema_linking"], knowledge)
            prompts[qid] = {
                "user_prompt": result["user_prompt"],
                "selected_tables": result["selected_tables"],
                "query_pattern": result["query_pattern"],
                "ddl_chars": result["ddl_chars"],
            }
            stats["total_ddl_chars"] += result["ddl_chars"]
            stats["avg_tables"] += len(result["selected_tables"])

        stats["avg_tables"] = round(stats["avg_tables"] / len(cases), 1)
        stats["avg_ddl_chars"] = round(stats["total_ddl_chars"] / len(cases))

        output = {
            "_meta": {
                "config": cfg_key,
                "name": cfg["name"],
                "schema_linking": cfg["schema_linking"],
                "knowledge": cfg["knowledge"],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "stats": stats,
            },
            "prompts": prompts,
        }
        path = PROJECT_ROOT / "eval" / f"prompts_{cfg['name']}.json"
        with open(path, "w") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[{cfg_key}] {cfg['name']}: avg {stats['avg_tables']} tables, {stats['avg_ddl_chars']} chars/prompt → {path.name}")

    # 生成 full DDL 文件
    full_ddl = mdl_to_ddl(mdl)
    with open(PROJECT_ROOT / "eval" / "full_ddl.sql", "w") as f:
        f.write(full_ddl)
    print(f"\nfull_ddl.sql: {len(full_ddl)} chars")


if __name__ == "__main__":
    main()
