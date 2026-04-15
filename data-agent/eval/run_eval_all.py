"""
一键评测 4 组实验 + 合并结果到 1 个 JSON + 生成 MD 报告

用法: python eval/run_eval_all.py
"""
import json, sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from eval_framework import run_evaluation, print_report

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = PROJECT_ROOT / "eval"
DB_PATH = str(PROJECT_ROOT / "telecom" / "output" / "telecom_nms.duckdb")
TEST_PATH = EVAL_DIR / "telecom_test_cases_100.json"

EXPERIMENTS = {
    "A": {"file": "opus_v3_fullschema_no_knowledge_sqls.json", "label": "全量Schema 无知识"},
    "B": {"file": "opus_v3_fullschema_with_knowledge_sqls.json", "label": "全量Schema 有知识"},
    "C": {"file": "opus_v3_schemalink_no_knowledge_sqls.json", "label": "Schema Linking 无知识"},
    "D": {"file": "opus_v3_schemalink_with_knowledge_sqls.json", "label": "Schema Linking 有知识"},
}


def run_all():
    with open(TEST_PATH) as f:
        test_cases = json.load(f)

    all_results = {
        "_meta": {
            "model": "claude-opus-4-6",
            "test_cases": 100,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "db_path": DB_PATH,
        },
        "experiments": {},
    }

    for exp_key, exp in EXPERIMENTS.items():
        sql_path = EVAL_DIR / exp["file"]
        if not sql_path.exists():
            print(f"[{exp_key}] SKIP — {exp['file']} not found")
            continue

        with open(sql_path) as f:
            sqls = json.load(f)

        print(f"\n[{exp_key}] Evaluating {exp['label']}...")
        result = run_evaluation(test_cases, sqls, DB_PATH)
        print_report(result, f"{exp_key}_{exp['label']}")

        all_results["experiments"][exp_key] = {
            "label": exp["label"],
            "file": exp["file"],
            "summary": result["summary"],
            "details": result["details"],
        }

    # 保存合并结果
    output_path = EVAL_DIR / "eval_results_v3.json"
    with open(output_path, "w") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n合并结果: {output_path}")

    # 生成 MD 报告
    generate_report(all_results)
    return all_results


def generate_report(data):
    ts = data["_meta"]["timestamp"]
    exps = data["experiments"]

    # 读取 prompt 样例
    prompt_samples = {}
    for cfg_key in ["A", "C"]:
        name = {"A": "fullschema_no_knowledge", "C": "schemalink_no_knowledge"}[cfg_key]
        pf = EVAL_DIR / f"prompts_{name}.json"
        if pf.exists():
            with open(pf) as f:
                pd = json.load(f)
            # 取 Q01 的 prompt 前 800 字符作为样例
            q01 = pd.get("prompts", {}).get("Q07", {})
            prompt_samples[cfg_key] = q01.get("user_prompt", "")[:1200] + "\n... (truncated)"

    lines = []
    lines.append(f"# AB Test Report v3 — NL2SQL 4 组对照实验")
    lines.append(f"")
    lines.append(f"> 时间: {ts} | 模型: Claude Opus 4.6 | 题目: 100 题 | 数据: 时间戳已刷新至当天")
    lines.append(f"")

    # 实验设计
    lines.append(f"## 实验设计")
    lines.append(f"")
    lines.append(f"| 实验 | Schema 策略 | 知识注入 | Pipeline 预处理 |")
    lines.append(f"|------|------------|---------|----------------|")
    lines.append(f"| **A** | 全量 14 表 DDL (19715 chars) | 无 | 无 |")
    lines.append(f"| **B** | 全量 14 表 DDL (19715 chars) | 有 | 无 |")
    lines.append(f"| **C** | Schema Linking ~6 表 (4564 chars) | 无 | 表选择 + 列裁剪 + JOIN 路径 + 模式识别 |")
    lines.append(f"| **D** | Schema Linking ~6 表 (4564 chars) | 有 | 同 C + 知识注入 |")
    lines.append(f"")

    # Prompt 样例
    if prompt_samples:
        lines.append(f"## Prompt 样例 (Q07: 查询过去24小时CPU平均利用率超过80%的网元)")
        lines.append(f"")
        for cfg_key, sample in prompt_samples.items():
            label = {"A": "全量Schema", "C": "Schema Linking"}[cfg_key]
            lines.append(f"### {cfg_key}: {label}")
            lines.append(f"```")
            lines.append(sample)
            lines.append(f"```")
            lines.append(f"")

    # 核心结果表
    lines.append(f"## 核心结果")
    lines.append(f"")
    headers = ["指标"]
    for k in ["A", "B", "C", "D"]:
        if k in exps:
            headers.append(exps[k]["label"])
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["------"] * len(headers)) + "|")

    metrics = [
        ("可执行率", "exec_rate"),
        ("严格准确率", "accuracy_strict"),
        ("宽松准确率", "accuracy_verifiable"),
        ("无法验证(0行)", "unverifiable_rate"),
    ]
    for label, key in metrics:
        row = [label]
        for k in ["A", "B", "C", "D"]:
            if k in exps:
                row.append(exps[k]["summary"][key])
        lines.append("| " + " | ".join(row) + " |")
    lines.append(f"")

    # 多维评分
    lines.append(f"## 多维评分")
    lines.append(f"")
    headers2 = ["维度"] + [exps[k]["label"] for k in ["A","B","C","D"] if k in exps]
    lines.append("| " + " | ".join(headers2) + " |")
    lines.append("|" + "|".join(["------"] * len(headers2)) + "|")
    for dim, dlabel in [("total","总分"),("tables","表选择"),("columns","列选择"),
                         ("where","WHERE条件"),("joins","JOIN"),("aggregation","聚合")]:
        row = [dlabel]
        for k in ["A","B","C","D"]:
            if k in exps:
                v = exps[k]["summary"]["avg_component_scores"].get(dim, 0)
                row.append(f"{v:.2f}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append(f"")

    # 按难度
    lines.append(f"## 按难度对比（宽松准确率）")
    lines.append(f"")
    headers3 = ["难度"] + [exps[k]["label"] for k in ["A","B","C","D"] if k in exps]
    lines.append("| " + " | ".join(headers3) + " |")
    lines.append("|" + "|".join(["------"] * len(headers3)) + "|")
    for diff in ["Easy", "Medium", "Hard", "Extra Hard"]:
        row = [diff]
        for k in ["A","B","C","D"]:
            if k not in exps:
                continue
            by_d = defaultdict(int)
            for r in exps[k]["details"]:
                if r["difficulty"] == diff:
                    by_d["total"] += 1
                    by_d[r["verdict"]] += 1
            relaxed = by_d["correct"] + by_d["correct_relaxed"]
            verif = by_d["total"] - by_d["unverifiable"]
            pct = f"{100*relaxed/verif:.0f}%" if verif > 0 else "N/A"
            row.append(f"{relaxed}/{verif} ({pct})")
        lines.append("| " + " | ".join(row) + " |")
    lines.append(f"")

    # 知识注入 diff (B vs A)
    if "A" in exps and "B" in exps:
        lines.append(f"## 知识注入效果 (B vs A)")
        lines.append(f"")
        a_map = {r["id"]: r for r in exps["A"]["details"]}
        b_map = {r["id"]: r for r in exps["B"]["details"]}
        rank = {"correct":3, "correct_relaxed":2, "unverifiable":1, "wrong":0, "error":-1}
        improved = [(qid, a_map[qid], b_map[qid]) for qid in sorted(a_map)
                     if rank.get(b_map[qid]["verdict"],0) > rank.get(a_map[qid]["verdict"],0)]
        degraded = [(qid, a_map[qid], b_map[qid]) for qid in sorted(a_map)
                     if rank.get(b_map[qid]["verdict"],0) < rank.get(a_map[qid]["verdict"],0)]
        lines.append(f"改善 {len(improved)} 题, 退步 {len(degraded)} 题")
        lines.append(f"")
        if improved:
            lines.append(f"| 题号 | 难度 | A→B |")
            lines.append(f"|------|------|-----|")
            for qid, a, b in improved:
                lines.append(f"| {qid} | {a['difficulty']} | {a['verdict']} → {b['verdict']} |")
            lines.append(f"")
        if degraded:
            lines.append(f"退步:")
            lines.append(f"| 题号 | 难度 | A→B |")
            lines.append(f"|------|------|-----|")
            for qid, a, b in degraded:
                lines.append(f"| {qid} | {a['difficulty']} | {a['verdict']} → {b['verdict']} |")
            lines.append(f"")

    # Schema Linking diff (C vs A)
    if "A" in exps and "C" in exps:
        lines.append(f"## Schema Linking 效果 (C vs A)")
        lines.append(f"")
        c_map = {r["id"]: r for r in exps["C"]["details"]}
        improved2 = [(qid, a_map[qid], c_map[qid]) for qid in sorted(a_map)
                      if rank.get(c_map[qid]["verdict"],0) > rank.get(a_map[qid]["verdict"],0)]
        degraded2 = [(qid, a_map[qid], c_map[qid]) for qid in sorted(a_map)
                      if rank.get(c_map[qid]["verdict"],0) < rank.get(a_map[qid]["verdict"],0)]
        lines.append(f"改善 {len(improved2)} 题, 退步 {len(degraded2)} 题")
        lines.append(f"")
        if improved2:
            lines.append(f"| 题号 | 难度 | A→C |")
            lines.append(f"|------|------|-----|")
            for qid, a, c in improved2:
                lines.append(f"| {qid} | {a['difficulty']} | {a['verdict']} → {c['verdict']} |")
            lines.append(f"")
        if degraded2:
            lines.append(f"退步:")
            lines.append(f"| 题号 | 难度 | A→C |")
            lines.append(f"|------|------|-----|")
            for qid, a, c in degraded2:
                lines.append(f"| {qid} | {a['difficulty']} | {a['verdict']} → {c['verdict']} |")
            lines.append(f"")

    # D 执行失败分析
    if "D" in exps:
        errors = [r for r in exps["D"]["details"] if r["verdict"] == "error"]
        if errors:
            lines.append(f"## D 组执行失败分析 ({len(errors)} 题)")
            lines.append(f"")
            lines.append(f"| 题号 | 难度 | 原因 |")
            lines.append(f"|------|------|------|")
            for r in errors:
                reason = r["reason"][:80]
                lines.append(f"| {r['id']} | {r['difficulty']} | {reason} |")
            lines.append(f"")

    report_path = EVAL_DIR / "AB_TEST_REPORT_v3.md"
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"报告: {report_path}")


if __name__ == "__main__":
    run_all()
