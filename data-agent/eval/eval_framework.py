"""
NL2SQL 评测框架
- 从 MDL 提取 DDL
- 在 DuckDB 上执行 SQL 并对比结果
- sqlglot 多维组件评分（表/列/条件/JOIN/聚合）
- 生成评测报告
"""

import json
import duckdb
import sys
from pathlib import Path

try:
    import sqlglot
    from sqlglot import exp as sqlexp
    HAS_SQLGLOT = True
except ImportError:
    HAS_SQLGLOT = False

# 项目根目录（eval/ 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ─── DDL 提取 ───

def mdl_to_ddl(mdl_path: str) -> str:
    """从 telecom_mdl.json 提取纯 DDL 文本（含中文描述）"""
    with open(mdl_path) as f:
        mdl = json.load(f)

    ddl_parts = []

    for model in mdl.get("models", []):
        table_name = model["name"]
        desc = model.get("properties", {}).get("description", "")
        columns = []
        for col in model.get("columns", []):
            if col.get("isHidden"):
                continue
            col_name = col["name"]
            col_type = col["type"]
            col_desc = col.get("properties", {}).get("description", "")
            pk = " PRIMARY KEY" if col_name == model.get("primaryKey") else ""
            not_null = " NOT NULL" if col.get("notNull") else ""
            comment = f"  -- {col_desc}" if col_desc else ""
            columns.append(f"  {col_name} {col_type}{pk}{not_null},{comment}")

        cols_str = "\n".join(columns)
        table_comment = f"-- {desc}" if desc else ""
        ddl_parts.append(f"{table_comment}\nCREATE TABLE {table_name} (\n{cols_str}\n);")

    # Relationships as comments
    rels = mdl.get("relationships", [])
    if rels:
        ddl_parts.append("\n-- ═══ RELATIONSHIPS (FOREIGN KEYS) ═══")
        for rel in rels:
            condition = rel.get("condition", "")
            join_type = rel.get("joinType", "")
            desc = rel.get("properties", {}).get("description", "")
            ddl_parts.append(f"-- {condition}  ({join_type})  {desc}")

    return "\n\n".join(ddl_parts)


# ─── SQL 执行与对比 ───

def execute_sql(conn: duckdb.DuckDBPyConnection, sql: str) -> dict:
    """执行 SQL，返回结果或错误"""
    try:
        result = conn.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return {"ok": True, "columns": columns, "rows": rows, "row_count": len(rows)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def compare_results(generated: dict, expected: dict) -> dict:
    """对比两个 SQL 的执行结果，三层判定：
    - correct: 值集合完全一致（业界 EX 标准）
    - correct_relaxed: 行数相同，期望行的值是生成行值的子集（列不同但数据对）
    - wrong: 真正的逻辑错误
    """
    if not generated["ok"]:
        return {"match": False, "verdict": "error", "reason": f"生成SQL执行失败: {generated['error']}"}
    if not expected["ok"]:
        return {"match": False, "verdict": "error", "reason": f"期望SQL执行失败: {expected['error']}"}

    gen_rows = generated["row_count"]
    exp_rows = expected["row_count"]

    # 两边都是 0 行 — 无法验证
    if gen_rows == 0 and exp_rows == 0:
        cols_match = generated["columns"] == expected["columns"]
        return {
            "match": False,
            "verdict": "unverifiable",
            "reason": f"双方均0行，无法验证语义正确性 (列{'一致' if cols_match else '不一致'})",
            "columns_match": cols_match,
        }

    # 列名对比（用于诊断）
    gen_cols = generated["columns"]
    exp_cols = expected["columns"]
    cols_same = gen_cols == exp_cols
    col_diff_note = ""
    if not cols_same:
        gen_only = set(gen_cols) - set(exp_cols)
        exp_only = set(exp_cols) - set(gen_cols)
        parts = []
        if exp_only:
            parts.append(f"缺列{exp_only}")
        if gen_only:
            parts.append(f"多列{gen_only}")
        col_diff_note = f" [列差异: {'; '.join(parts)}]"

    if gen_rows != exp_rows:
        return {
            "match": False,
            "verdict": "wrong",
            "reason": f"行数不同: 生成{gen_rows}行 vs 期望{exp_rows}行{col_diff_note}",
        }

    # 转成可比较的集合（忽略列名差异，只比值）
    gen_set = set(tuple(str(v) for v in row) for row in generated["rows"])
    exp_set = set(tuple(str(v) for v in row) for row in expected["rows"])

    if gen_set == exp_set:
        return {"match": True, "verdict": "correct", "reason": "完全匹配"}

    # ── 宽松匹配：行数相同但列不同，检查值子集关系 ──
    if gen_rows == exp_rows and gen_rows > 0:
        matched_rows = 0
        for exp_row in expected["rows"]:
            exp_vals = set(str(v) for v in exp_row if v is not None and str(v).strip())
            for gen_row in generated["rows"]:
                gen_vals = set(str(v) for v in gen_row if v is not None and str(v).strip())
                if exp_vals <= gen_vals or gen_vals <= exp_vals:
                    matched_rows += 1
                    break
        if matched_rows == exp_rows:
            return {
                "match": True,
                "verdict": "correct_relaxed",
                "reason": f"逻辑正确，列选择不同({gen_rows}行){col_diff_note}",
            }

    overlap = gen_set & exp_set
    only_gen = gen_set - exp_set
    only_exp = exp_set - gen_set
    # 诊断：行数相同但值不同 → 通常是 WHERE/JOIN 条件偏差
    if gen_rows == exp_rows:
        diag = f"行数相同({gen_rows}行)但值不同: {len(overlap)}行重合{col_diff_note}"
    else:
        diag = f"{len(overlap)}行重合, 多{len(only_gen)}行, 缺{len(only_exp)}行{col_diff_note}"
    return {
        "match": False,
        "verdict": "wrong",
        "reason": diag,
    }


# ─── sqlglot 多维评分 ───

def _expand_ctes(parsed):
    """展开 CTE (WITH ... AS) 以便公平比较 CTE 和非 CTE 写法。
    返回展开后的 AST（best-effort，失败则返回原 AST）。
    """
    try:
        # 收集所有 CTE 定义
        ctes = {}
        for cte in parsed.find_all(sqlexp.CTE):
            alias = cte.alias
            if alias:
                ctes[str(alias).strip('"').lower()] = cte.this  # the subquery body

        if not ctes:
            return parsed

        # 用 sqlglot 的 transform 递归替换 CTE 引用为内联子查询
        def _replace_cte_refs(node):
            if isinstance(node, sqlexp.Table):
                name = str(node.this).strip('"').lower()
                if name in ctes:
                    # 替换为子查询
                    subq = sqlexp.Subquery(this=ctes[name].copy())
                    if node.alias:
                        subq.set("alias", node.alias)
                    else:
                        subq.set("alias", sqlexp.TableAlias(this=sqlexp.Identifier(this=name)))
                    return subq
            return node

        expanded = parsed.copy()
        # 移除 WITH 子句
        expanded_with = expanded.find(sqlexp.With)
        if expanded_with:
            expanded_with.pop()
        expanded = expanded.transform(_replace_cte_refs)
        return expanded
    except Exception:
        return parsed


def _normalize_col_name(col_str: str) -> str:
    """标准化列名用于模糊匹配。去除常见后缀差异和下划线变体。"""
    s = col_str.lower().strip().strip('"')
    # 去掉聚合函数包装，保留内容
    # 例如 "avg(cpu_usage_avg_pct)" -> "cpu_usage_avg_pct"
    import re
    agg_match = re.match(r'(count|sum|avg|min|max|round)\((.+)\)', s)
    if agg_match:
        s = agg_match.group(2).strip()
        # round 可能嵌套: round(avg(x), 2) -> avg(x) -> x
        agg_match2 = re.match(r'(count|sum|avg|min|max)\((.+)\)', s)
        if agg_match2:
            s = agg_match2.group(2).split(',')[0].strip()
    # 去表前缀
    if '.' in s and '(' not in s:
        s = s.split('.')[-1]
    return s.strip('"').strip()


def _fuzzy_col_jaccard(gen_cols: set, exp_cols: set) -> float:
    """模糊列名匹配的 Jaccard 相似度。
    先精确匹配，再对未匹配的做标准化匹配。
    """
    if not gen_cols and not exp_cols:
        return 1.0

    gen_norm = {_normalize_col_name(c): c for c in gen_cols}
    exp_norm = {_normalize_col_name(c): c for c in exp_cols}

    # 精确匹配
    exact_match = set(gen_norm.keys()) & set(exp_norm.keys())

    # 对未匹配的做更模糊的匹配（去掉 _count/_pct/_avg/_max 等后缀）
    import re
    def _stem(s):
        # 去掉常见数值后缀
        s = re.sub(r'_(count|pct|avg|max|min|rate|ratio|num|total|sum)$', '', s)
        # 去掉前缀如 avg_, max_, total_
        s = re.sub(r'^(avg|max|min|total|sum|count)_', '', s)
        return s

    gen_unmatched = set(gen_norm.keys()) - exact_match
    exp_unmatched = set(exp_norm.keys()) - exact_match
    fuzzy_match = 0
    gen_used = set()
    for ec in exp_unmatched:
        ec_stem = _stem(ec)
        for gc in gen_unmatched:
            if gc not in gen_used:
                gc_stem = _stem(gc)
                if ec_stem == gc_stem or ec_stem in gc or gc_stem in ec:
                    fuzzy_match += 1
                    gen_used.add(gc)
                    break

    matched = len(exact_match) + fuzzy_match
    total = len(set(gen_norm.keys()) | set(exp_norm.keys()))
    return matched / total if total > 0 else 1.0


def _extract_sql_components(sql: str) -> dict | None:
    """从 SQL 中提取结构化组件用于评分。
    改进: CTE 展开后提取，避免 CTE 写法被低估。
    """
    if not HAS_SQLGLOT:
        return None
    try:
        parsed = sqlglot.parse_one(sql, dialect="duckdb")
    except Exception:
        return None

    # CTE 展开 — 从展开后的 AST 提取组件
    expanded = _expand_ctes(parsed)

    # 收集 CTE 别名（排除它们不算真实表名）
    cte_names = set()
    for cte in parsed.find_all(sqlexp.CTE):
        alias = cte.alias
        if alias:
            cte_names.add(str(alias).strip('"').lower())

    # 表名（去引号，小写）— 从原始和展开后都提取，排除 CTE 别名
    tables = set()
    for tree in [parsed, expanded]:
        for t in tree.find_all(sqlexp.Table):
            name = str(t.this).strip('"').lower()
            if name and not name.startswith("(") and name not in cte_names:
                tables.add(name)

    # SELECT 列（去表前缀和别名，小写）
    select_cols = set()
    for s in parsed.selects:
        col_str = str(s).lower()
        # 提取别名
        if " as " in col_str:
            col_str = col_str.split(" as ")[-1].strip().strip('"')
        elif "." in col_str and "(" not in col_str:
            col_str = col_str.split(".")[-1].strip('"')
        select_cols.add(col_str.strip())

    # WHERE 条件 — 从原始和展开后的 AST 都提取
    where_conditions = set()
    for tree in [parsed, expanded]:
        for where in tree.find_all(sqlexp.Where):
            for eq in where.find_all(sqlexp.EQ):
                left = str(eq.left).lower().split(".")[-1].strip('"')
                right = str(eq.right).strip("'\"").upper()
                # 标准化布尔: field=TRUE → field_BOOL, field=FALSE → NOT_field
                if right in ('TRUE', '1'):
                    where_conditions.add(f"{left}_BOOL")
                elif right in ('FALSE', '0'):
                    where_conditions.add(f"NOT_{left}")
                else:
                    where_conditions.add(f"{left}={right}")
            for cmp in where.find_all((sqlexp.GT, sqlexp.GTE, sqlexp.LT, sqlexp.LTE)):
                left = str(cmp.left).lower().split(".")[-1].strip('"')
                op = {sqlexp.GT: ">", sqlexp.GTE: ">=", sqlexp.LT: "<", sqlexp.LTE: "<="}.get(type(cmp), "?")
                where_conditions.add(f"{left}{op}...")
            for is_node in where.find_all(sqlexp.Is):
                left = str(is_node.this).lower().split(".")[-1].strip('"')
                where_conditions.add(f"{left}_IS")
            for not_node in where.find_all(sqlexp.Not):
                child = not_node.this
                if isinstance(child, sqlexp.Column):
                    # WHERE NOT field → NOT_field（等价于 field=FALSE）
                    col_name = str(child).lower().split(".")[-1].strip('"')
                    where_conditions.add(f"NOT_{col_name}")
                elif isinstance(child, sqlexp.Paren):
                    # WHERE NOT (field) 也可能出现
                    inner = child.this
                    if isinstance(inner, sqlexp.Column):
                        col_name = str(inner).lower().split(".")[-1].strip('"')
                        where_conditions.add(f"NOT_{col_name}")
            # 裸布尔列: WHERE field_name（无比较操作符）
            # sqlglot 解析为 Column 节点直接在 Where 的条件中
            for col in where.find_all(sqlexp.Column):
                # 检查这个 Column 是否直接作为布尔条件（不在 EQ/比较操作符内部）
                parent = col.parent
                if parent and isinstance(parent, (sqlexp.And, sqlexp.Or, sqlexp.Where)):
                    col_name = str(col).lower().split(".")[-1].strip('"')
                    where_conditions.add(f"{col_name}_BOOL")

    # HAVING 条件也提取（补充 WHERE）— 标准化左侧表达式
    for tree in [parsed, expanded]:
        for having in tree.find_all(sqlexp.Having):
            for cmp in having.find_all((sqlexp.GT, sqlexp.GTE, sqlexp.LT, sqlexp.LTE)):
                left_raw = str(cmp.left).lower()
                # 提取聚合函数内的列名: AVG(k.col) -> col
                import re as _re
                agg_m = _re.search(r'(?:avg|sum|count|max|min)\(([^)]+)\)', left_raw)
                if agg_m:
                    left = agg_m.group(1).split(".")[-1].strip('"')
                else:
                    left = left_raw.split(".")[-1].strip('"')
                op = {sqlexp.GT: ">", sqlexp.GTE: ">=", sqlexp.LT: "<", sqlexp.LTE: "<="}.get(type(cmp), "?")
                where_conditions.add(f"{left}{op}...")

    # JOIN 关联表 — 包含 FROM 表 + JOIN 表（FROM a JOIN b 与 FROM b JOIN a 语义相同）
    join_tables = set()
    for tree in [parsed, expanded]:
        # FROM 后面的主表也算关联表
        from_clause = tree.find(sqlexp.From)
        if from_clause:
            for t in from_clause.find_all(sqlexp.Table):
                name = str(t.this).strip('"').lower()
                if name and name not in cte_names:
                    join_tables.add(name)
        # JOIN 表
        for join in tree.find_all(sqlexp.Join):
            t = join.find(sqlexp.Table)
            if t:
                name = str(t.this).strip('"').lower()
                if name not in cte_names:
                    join_tables.add(name)

    # GROUP BY 列 — 从原始和展开后都提取
    group_cols = set()
    for tree in [parsed, expanded]:
        group = tree.find(sqlexp.Group)
        if group:
            for g in group.expressions:
                col_str = str(g).lower().split(".")[-1].strip('"')
                if " as " in col_str:
                    col_str = col_str.split(" as ")[0].strip()
                group_cols.add(col_str)

    # 结构特征
    has_having = parsed.find(sqlexp.Having) is not None or expanded.find(sqlexp.Having) is not None
    has_order = parsed.find(sqlexp.Order) is not None
    has_limit = parsed.find(sqlexp.Limit) is not None
    has_cte = parsed.find(sqlexp.CTE) is not None
    has_subquery = len(list(parsed.find_all(sqlexp.Subquery))) > 0

    return {
        "tables": tables,
        "select_cols": select_cols,
        "where_conditions": where_conditions,
        "join_tables": join_tables,
        "group_cols": group_cols,
        "has_having": has_having,
        "has_order": has_order,
        "has_limit": has_limit,
        "has_cte": has_cte,
        "has_subquery": has_subquery,
    }


def _jaccard(set_a: set, set_b: set) -> float:
    """Jaccard 相似度"""
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 1.0
    return len(set_a & set_b) / len(union)


def _recall(gen_set: set, exp_set: set) -> float:
    """召回率：期望的有多少被生成覆盖了"""
    if not exp_set:
        return 1.0
    return len(gen_set & exp_set) / len(exp_set)


def score_sql_components(gen_sql: str, exp_sql: str) -> dict | None:
    """多维 SQL 组件评分

    返回:
        {
            "scores": {
                "tables": 0.0-1.0,    # 表选择
                "columns": 0.0-1.0,   # 列选择
                "where": 0.0-1.0,     # WHERE 条件
                "joins": 0.0-1.0,     # JOIN 关系
                "aggregation": 0.0-1.0, # 聚合逻辑
            },
            "total": 0.0-1.0,        # 加权总分
            "gen_components": {...},   # 生成 SQL 的组件
            "exp_components": {...},   # 期望 SQL 的组件
        }
    """
    gen_comp = _extract_sql_components(gen_sql)
    exp_comp = _extract_sql_components(exp_sql)

    if not gen_comp or not exp_comp:
        return None

    scores = {}

    # 1. 表选择 — Jaccard
    scores["tables"] = round(_jaccard(gen_comp["tables"], exp_comp["tables"]), 2)

    # 2. 列选择 — 模糊 Jaccard（处理别名差异、后缀差异）
    scores["columns"] = round(_fuzzy_col_jaccard(gen_comp["select_cols"], exp_comp["select_cols"]), 2)

    # 3. WHERE 条件 — 召回率（期望的条件是否都有）
    if exp_comp["where_conditions"]:
        scores["where"] = round(_recall(gen_comp["where_conditions"], exp_comp["where_conditions"]), 2)
    else:
        scores["where"] = 1.0 if not gen_comp["where_conditions"] else 0.5

    # 4. JOIN — Jaccard
    if exp_comp["join_tables"] or gen_comp["join_tables"]:
        scores["joins"] = round(_jaccard(gen_comp["join_tables"], exp_comp["join_tables"]), 2)
    else:
        scores["joins"] = 1.0

    # 5. 聚合逻辑 — GROUP BY 列 Jaccard + HAVING 一致性
    if exp_comp["group_cols"] or gen_comp["group_cols"]:
        group_score = _jaccard(gen_comp["group_cols"], exp_comp["group_cols"])
        having_match = 1.0 if gen_comp["has_having"] == exp_comp["has_having"] else 0.5
        scores["aggregation"] = round(group_score * 0.7 + having_match * 0.3, 2)
    else:
        scores["aggregation"] = 1.0

    # 加权总分
    weights = {
        "tables": 0.15,
        "columns": 0.20,
        "where": 0.30,
        "joins": 0.15,
        "aggregation": 0.20,
    }
    total = round(sum(scores[k] * weights[k] for k in weights), 2)

    return {
        "scores": scores,
        "total": total,
        "gen_components": {k: list(v) if isinstance(v, set) else v for k, v in gen_comp.items()},
        "exp_components": {k: list(v) if isinstance(v, set) else v for k, v in exp_comp.items()},
    }


# ─── 评测运行器 ───

def run_evaluation(test_cases: list, generated_sqls: dict, db_path: str) -> dict:
    """
    运行评测：结果集匹配 + 多维组件评分
    """
    conn = duckdb.connect(db_path, read_only=True)
    results = []

    for case in test_cases:
        qid = case["id"]
        gen_sql = generated_sqls.get(qid, "")

        if not gen_sql:
            results.append({
                "id": qid,
                "question": case["question"],
                "difficulty": case.get("difficulty", ""),
                "executable": False,
                "correct": False,
                "verdict": "error",
                "reason": "未生成SQL",
                "generated_sql": "",
                "expected_sql": case["expected_sql"],
                "component_scores": None,
            })
            continue

        gen_result = execute_sql(conn, gen_sql)
        exp_result = execute_sql(conn, case["expected_sql"])
        comparison = compare_results(gen_result, exp_result)

        # 多维组件评分
        component_scores = score_sql_components(gen_sql, case["expected_sql"])

        verdict = comparison.get("verdict", "wrong")
        results.append({
            "id": qid,
            "question": case["question"],
            "difficulty": case.get("difficulty", ""),
            "executable": gen_result["ok"],
            "correct": comparison["match"],
            "verdict": verdict,
            "reason": comparison["reason"],
            "generated_sql": gen_sql,
            "expected_sql": case["expected_sql"],
            "gen_columns": gen_result.get("columns", []),
            "exp_columns": exp_result.get("columns", []),
            "gen_row_count": gen_result.get("row_count", 0) if gen_result["ok"] else -1,
            "exp_row_count": exp_result.get("row_count", 0) if exp_result["ok"] else -1,
            "component_scores": component_scores,
        })

    conn.close()

    # 汇总
    total = len(results)
    executable = sum(1 for r in results if r["executable"])
    correct_strict = sum(1 for r in results if r["verdict"] == "correct")
    correct_relaxed = sum(1 for r in results if r["verdict"] == "correct_relaxed")
    correct_all = correct_strict + correct_relaxed
    unverifiable = sum(1 for r in results if r["verdict"] == "unverifiable")
    wrong = sum(1 for r in results if r["verdict"] == "wrong")
    error = sum(1 for r in results if r["verdict"] == "error")
    verifiable = total - unverifiable
    pct = lambda n, d: f"{100*n/d:.0f}%" if d > 0 else "N/A"

    # 组件评分汇总
    scored = [r for r in results if r["component_scores"]]
    avg_scores = {}
    if scored:
        for dim in ["tables", "columns", "where", "joins", "aggregation"]:
            vals = [r["component_scores"]["scores"][dim] for r in scored]
            avg_scores[dim] = round(sum(vals) / len(vals), 2)
        total_vals = [r["component_scores"]["total"] for r in scored]
        avg_scores["total"] = round(sum(total_vals) / len(total_vals), 2)

    return {
        "summary": {
            "total": total,
            "executable": executable,
            "correct": correct_strict,
            "correct_relaxed": correct_relaxed,
            "correct_all": correct_all,
            "unverifiable": unverifiable,
            "wrong": wrong,
            "error": error,
            "exec_rate": f"{executable}/{total} ({pct(executable, total)})",
            "accuracy_strict": f"{correct_strict}/{total} ({pct(correct_strict, total)})",
            "accuracy_relaxed": f"{correct_all}/{total} ({pct(correct_all, total)})",
            "accuracy_verifiable": f"{correct_all}/{verifiable} ({pct(correct_all, verifiable)})" if verifiable > 0 else "N/A",
            "unverifiable_rate": f"{unverifiable}/{total} ({pct(unverifiable, total)})",
            "avg_component_scores": avg_scores,
        },
        "details": results,
    }


def print_report(eval_result: dict, experiment_name: str = ""):
    """打印评测报告"""
    s = eval_result["summary"]
    print(f"\n{'═'*70}")
    print(f"  评测报告: {experiment_name}")
    print(f"{'═'*70}")
    print(f"  可执行率:        {s['exec_rate']}")
    print(f"  准确率(严格):    {s['accuracy_strict']}")
    print(f"  准确率(可验证):  {s['accuracy_verifiable']}")
    print(f"  无法验证(0行):   {s['unverifiable_rate']}")

    # 组件评分
    avg = s.get("avg_component_scores", {})
    if avg:
        print(f"{'─'*70}")
        print(f"  多维评分(平均):  总分 {avg.get('total',0):.2f}")
        print(f"    表选择  {avg.get('tables',0):.2f}  |  "
              f"列选择  {avg.get('columns',0):.2f}  |  "
              f"WHERE  {avg.get('where',0):.2f}  |  "
              f"JOIN   {avg.get('joins',0):.2f}  |  "
              f"聚合   {avg.get('aggregation',0):.2f}")
        print(f"    权重:   表15%       列20%       条件30%     JOIN15%     聚合20%")

    print(f"{'─'*70}")

    # 按难度汇总
    from collections import defaultdict
    by_diff = defaultdict(lambda: {"total": 0, "correct": 0, "correct_relaxed": 0, "unverifiable": 0, "wrong": 0, "error": 0, "scores": []})
    for r in eval_result["details"]:
        d = r.get("difficulty", "Unknown")
        by_diff[d]["total"] += 1
        by_diff[d][r["verdict"]] += 1
        if r.get("component_scores"):
            by_diff[d]["scores"].append(r["component_scores"]["total"])

    print(f"  {'难度':12s} {'总数':>4s} {'正确':>4s} {'错误':>4s} {'不可验证':>8s} {'执行失败':>8s} {'严格准确率':>10s} {'平均评分':>8s}")
    for d in ["Easy", "Medium", "Hard", "Extra Hard"]:
        if d not in by_diff:
            continue
        b = by_diff[d]
        verif = b["total"] - b["unverifiable"]
        rate = f"{100*b['correct']/verif:.0f}%" if verif > 0 else "N/A"
        avg_score = f"{sum(b['scores'])/len(b['scores']):.2f}" if b["scores"] else "N/A"
        print(f"  {d:12s} {b['total']:4d} {b['correct']:4d} {b['wrong']:4d} {b['unverifiable']:8d} {b['error']:8d} {rate:>10s} {avg_score:>8s}")

    print(f"{'─'*70}")

    # 逐题详情
    symbols = {"correct": "✅", "unverifiable": "🔘", "wrong": "⚠️", "error": "❌"}
    for r in eval_result["details"]:
        sym = symbols.get(r["verdict"], "?")
        cs = r.get("component_scores")
        score_str = f" 评分:{cs['total']:.2f}" if cs else ""
        dim_str = ""
        if cs:
            sc = cs["scores"]
            dim_str = f" T:{sc['tables']:.1f} C:{sc['columns']:.1f} W:{sc['where']:.1f} J:{sc['joins']:.1f} A:{sc['aggregation']:.1f}"

        print(f"  {sym} {r['id']} [{r.get('difficulty','')}]{score_str}{dim_str}  {r['question'][:35]}...")
        if r["verdict"] != "correct":
            print(f"     {r['reason']}")
    print()


# ─── 入口 ───

if __name__ == "__main__":
    eval_dir = Path(__file__).resolve().parent
    db_path = str(PROJECT_ROOT / "telecom" / "output" / "telecom_nms.duckdb")
    mdl_path = str(PROJECT_ROOT / "telecom" / "input" / "telecom_mdl.json")
    test_cases_path = str(eval_dir / "telecom_test_cases_100.json")

    if len(sys.argv) < 2:
        ddl = mdl_to_ddl(mdl_path)
        print(ddl)
        sys.exit(0)

    generated_file = sys.argv[1]
    if not Path(generated_file).is_absolute():
        generated_file = str(Path.cwd() / generated_file)
    exp_name = sys.argv[2] if len(sys.argv) > 2 else "unnamed"

    with open(test_cases_path) as f:
        test_cases = json.load(f)
    with open(generated_file) as f:
        generated_sqls = json.load(f)

    result = run_evaluation(test_cases, generated_sqls, db_path)
    print_report(result, exp_name)

    output_file = str(eval_dir / f"eval_result_{exp_name}.json")
    with open(output_file, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"详细结果已保存到 {output_file}")
