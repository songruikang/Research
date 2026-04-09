"""
NL2SQL 评测框架
- 从 MDL 提取 DDL
- 在 DuckDB 上执行 SQL 并对比结果
- 生成评测报告
"""

import json
import duckdb
import sys
from pathlib import Path

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
    """对比两个 SQL 的执行结果，区分真正匹配 vs 空集匹配"""
    if not generated["ok"]:
        return {"match": False, "verdict": "error", "reason": f"生成SQL执行失败: {generated['error']}"}
    if not expected["ok"]:
        return {"match": False, "verdict": "error", "reason": f"期望SQL执行失败: {expected['error']}"}

    gen_rows = generated["row_count"]
    exp_rows = expected["row_count"]

    # 两边都是 0 行 — 无法验证
    if gen_rows == 0 and exp_rows == 0:
        # 检查列是否一致（至少能验证 schema 理解）
        cols_match = generated["columns"] == expected["columns"]
        return {
            "match": False,  # 不算正确
            "verdict": "unverifiable",
            "reason": f"双方均0行，无法验证语义正确性 (列{'一致' if cols_match else '不一致'})",
            "columns_match": cols_match,
        }

    if gen_rows != exp_rows:
        return {
            "match": False,
            "verdict": "wrong",
            "reason": f"行数不同: 生成{gen_rows}行 vs 期望{exp_rows}行",
        }

    # 转成可比较的集合（忽略列名差异，只比值）
    gen_set = set(tuple(str(v) for v in row) for row in generated["rows"])
    exp_set = set(tuple(str(v) for v in row) for row in expected["rows"])

    if gen_set == exp_set:
        return {"match": True, "verdict": "correct", "reason": "完全匹配"}

    # 部分匹配分析
    overlap = gen_set & exp_set
    only_gen = gen_set - exp_set
    only_exp = exp_set - gen_set
    return {
        "match": False,
        "verdict": "wrong",
        "reason": f"值不同: {len(overlap)}行匹配, 生成多{len(only_gen)}行, 缺少{len(only_exp)}行",
    }


# ─── 评测运行器 ───

def run_evaluation(test_cases: list, generated_sqls: dict, db_path: str) -> dict:
    """
    运行评测
    test_cases: [{id, question, expected_sql, ...}]
    generated_sqls: {question_id: sql_string}
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
                "executable": False,
                "correct": False,
                "reason": "未生成SQL",
                "generated_sql": "",
                "expected_sql": case["expected_sql"],
            })
            continue

        gen_result = execute_sql(conn, gen_sql)
        exp_result = execute_sql(conn, case["expected_sql"])
        comparison = compare_results(gen_result, exp_result)

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
        })

    conn.close()

    # 汇总（三级指标）
    total = len(results)
    executable = sum(1 for r in results if r["executable"])
    correct = sum(1 for r in results if r["verdict"] == "correct")
    unverifiable = sum(1 for r in results if r["verdict"] == "unverifiable")
    wrong = sum(1 for r in results if r["verdict"] == "wrong")
    error = sum(1 for r in results if r["verdict"] == "error")
    verifiable = total - unverifiable
    pct = lambda n, d: f"{100*n/d:.0f}%" if d > 0 else "N/A"

    return {
        "summary": {
            "total": total,
            "executable": executable,
            "correct": correct,
            "unverifiable": unverifiable,
            "wrong": wrong,
            "error": error,
            "exec_rate": f"{executable}/{total} ({pct(executable, total)})",
            "accuracy_strict": f"{correct}/{total} ({pct(correct, total)})",
            "accuracy_verifiable": f"{correct}/{verifiable} ({pct(correct, verifiable)})" if verifiable > 0 else "N/A",
            "unverifiable_rate": f"{unverifiable}/{total} ({pct(unverifiable, total)})",
        },
        "details": results,
    }


def print_report(eval_result: dict, experiment_name: str = ""):
    """打印评测报告"""
    s = eval_result["summary"]
    print(f"\n{'═'*60}")
    print(f"  评测报告: {experiment_name}")
    print(f"{'═'*60}")
    print(f"  可执行率:        {s['exec_rate']}")
    print(f"  准确率(严格):    {s['accuracy_strict']}")
    print(f"  准确率(可验证):  {s['accuracy_verifiable']}")
    print(f"  无法验证(0行):   {s['unverifiable_rate']}")
    print(f"{'─'*60}")

    # 按难度汇总
    from collections import defaultdict
    by_diff = defaultdict(lambda: {"total": 0, "correct": 0, "unverifiable": 0, "wrong": 0, "error": 0})
    for r in eval_result["details"]:
        d = r.get("difficulty", "Unknown")
        by_diff[d]["total"] += 1
        by_diff[d][r["verdict"]] += 1

    print(f"  {'难度':12s} {'总数':>4s} {'正确':>4s} {'错误':>4s} {'无法验证':>8s} {'执行失败':>8s} {'可验证准确率':>12s}")
    for d in ["Easy", "Medium", "Hard", "Extra Hard"]:
        if d not in by_diff:
            continue
        b = by_diff[d]
        verif = b["total"] - b["unverifiable"]
        rate = f"{100*b['correct']/verif:.0f}%" if verif > 0 else "N/A"
        print(f"  {d:12s} {b['total']:4d} {b['correct']:4d} {b['wrong']:4d} {b['unverifiable']:8d} {b['error']:8d} {rate:>12s}")
    print(f"{'─'*60}")

    # 逐题详情
    symbols = {"correct": "✅", "unverifiable": "🔘", "wrong": "⚠️", "error": "❌"}
    for r in eval_result["details"]:
        sym = symbols.get(r["verdict"], "?")
        print(f"  {sym} {r['id']} [{r.get('difficulty','')}] {r['question'][:40]}...")
        if r["verdict"] != "correct":
            print(f"     {r['reason']}")
    print()


# ─── 入口 ───

if __name__ == "__main__":
    # 用法: python eval_framework.py <generated_sqls.json> [experiment_name]
    eval_dir = Path(__file__).resolve().parent
    db_path = str(PROJECT_ROOT / "telecom_nms.duckdb")
    mdl_path = str(PROJECT_ROOT / "telecom" / "telecom_mdl.json")
    test_cases_path = str(eval_dir / "telecom_test_cases_100.json")

    if len(sys.argv) < 2:
        # 默认模式：只生成 DDL
        ddl = mdl_to_ddl(mdl_path)
        print(ddl)
        sys.exit(0)

    generated_file = sys.argv[1]
    # 如果是相对路径，相对于 eval/ 目录
    if not Path(generated_file).is_absolute():
        generated_file = str(eval_dir / generated_file)
    exp_name = sys.argv[2] if len(sys.argv) > 2 else "unnamed"

    with open(test_cases_path) as f:
        test_cases = json.load(f)
    with open(generated_file) as f:
        generated_sqls = json.load(f)

    result = run_evaluation(test_cases, generated_sqls, db_path)
    print_report(result, exp_name)

    # 保存详细结果到 eval/ 目录
    output_file = str(eval_dir / f"eval_result_{exp_name}.json")
    with open(output_file, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"详细结果已保存到 {output_file}")
