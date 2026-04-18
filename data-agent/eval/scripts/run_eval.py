"""
统一评测脚本 — 加载 all_sqls.json → 选择实验组 → 执行评测 → 生成报告

用法:
  python eval/scripts/run_eval.py                    # 评测全部 6 组
  python eval/scripts/run_eval.py --exp 0 1 4 5      # 只跑第 0/1/4/5 组
  python eval/scripts/run_eval.py --exp 4             # 只跑第 4 组

实验索引对应关系见 results/all_sqls.json 中的 experiments 数组。
"""
import json, sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from eval_framework import run_evaluation, print_report

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EVAL_DIR = PROJECT_ROOT / "eval"
RESULTS_DIR = EVAL_DIR / "results"
GENERATED_DIR = EVAL_DIR / ".generated"
DB_PATH = str(PROJECT_ROOT / "telecom" / "output" / "telecom_nms.duckdb")
TEST_PATH = EVAL_DIR / "telecom_test_cases_100.json"
SQLS_PATH = RESULTS_DIR / "all_sqls.json"


def load_all_sqls() -> dict:
    """加载统一 SQL 文件"""
    if not SQLS_PATH.exists():
        print(f"ERROR: {SQLS_PATH} not found")
        sys.exit(1)
    with open(SQLS_PATH) as f:
        return json.load(f)


def run_eval(exp_indices: list[int] | None = None):
    """运行评测"""
    with open(TEST_PATH) as f:
        test_cases = json.load(f)

    data = load_all_sqls()
    experiments = data["experiments"]
    sqls = data["sqls"]

    # 确定要跑的实验索引
    if exp_indices is None:
        exp_indices = list(range(len(experiments)))

    for idx in exp_indices:
        if idx >= len(experiments):
            print(f"  [SKIP] 索引 {idx} 超出范围（共 {len(experiments)} 组）")
            continue

    all_results = {
        "_meta": {
            "test_cases": len(test_cases),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        },
        "experiments": {},
    }

    for idx in exp_indices:
        if idx >= len(experiments):
            continue
        exp = experiments[idx]
        label = exp["label"]

        # 提取该实验组的 per-question SQL（按 label 匹配）
        exp_sqls = {}
        for qid, sql_dict in sqls.items():
            if label in sql_dict and sql_dict[label]:
                exp_sqls[qid] = sql_dict[label]

        print(f"\n[{idx}] Evaluating {label} ({exp['model']})...")
        result = run_evaluation(test_cases, exp_sqls, DB_PATH)
        print_report(result, f"[{idx}] {label}")

        all_results["experiments"][str(idx)] = {
            "index": idx,
            "label": label,
            "model": exp["model"],
            "summary": result["summary"],
            "details": result["details"],
        }

    # 保存详细结果
    GENERATED_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    detail_path = GENERATED_DIR / f"eval_results_{ts}.json"
    with open(detail_path, "w") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果: {detail_path}")

    # 生成报告
    report_path = RESULTS_DIR / f"report_{ts}.md"
    generate_report(all_results, experiments, report_path)
    print(f"报告: {report_path}")


def generate_report(data, experiments, report_path: Path):
    """生成 Markdown 评测报告"""
    ts = data["_meta"]["timestamp"]
    exps = data["experiments"]
    order = sorted(exps.keys(), key=int)

    lines = []
    lines.append("# 评测报告")
    lines.append("")
    lines.append(f"> 时间: {ts} | 题目: {data['_meta']['test_cases']} 题")
    lines.append("")

    # 实验设计表
    lines.append("## 实验设计")
    lines.append("")
    lines.append("| 索引 | 模型 | Schema | Few-shot | 知识 | 说明 |")
    lines.append("|------|------|--------|----------|------|------|")
    for idx_str in order:
        idx = int(idx_str)
        exp = experiments[idx]
        schema = "全量 14 表" if exp["schema"] == "full" else "Schema Linking ~6 表"
        fs = "Top-3" if exp["few_shot"] else "无"
        kg = "有" if exp["knowledge"] else "无"
        lines.append(f"| {idx} | {exp['model']} | {schema} | {fs} | {kg} | {exp['label']} |")
    lines.append("")

    # 核心结果
    lines.append("## 核心结果")
    lines.append("")
    headers = ["指标"] + [exps[k]["label"] for k in order]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["------"] * len(headers)) + "|")
    for label, key in [("可执行率", "exec_rate"), ("准确率(EX)", "accuracy"),
                        ("准确率(可验证)", "accuracy_verifiable"), ("无法验证(0行)", "unverifiable_rate")]:
        row = [label] + [exps[k]["summary"][key] for k in order]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # 多维评分
    lines.append("## 多维评分")
    lines.append("")
    headers2 = ["维度"] + [exps[k]["label"] for k in order]
    lines.append("| " + " | ".join(headers2) + " |")
    lines.append("|" + "|".join(["------"] * len(headers2)) + "|")
    for dim, dlabel in [("total", "总分"), ("tables", "表选择"), ("columns", "列选择"),
                         ("where", "WHERE条件"), ("joins", "JOIN"), ("aggregation", "聚合")]:
        row = [dlabel]
        for k in order:
            v = exps[k]["summary"]["avg_component_scores"].get(dim, 0)
            row.append(f"{v:.2f}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # 按难度
    lines.append("## 按难度对比（EX 准确率）")
    lines.append("")
    headers3 = ["难度"] + [exps[k]["label"] for k in order]
    lines.append("| " + " | ".join(headers3) + " |")
    lines.append("|" + "|".join(["------"] * len(headers3)) + "|")
    for diff in ["Easy", "Medium", "Hard", "Extra Hard"]:
        row = [diff]
        for k in order:
            by_d = defaultdict(int)
            for r in exps[k]["details"]:
                if r["difficulty"] == diff:
                    by_d["total"] += 1
                    by_d[r["verdict"]] += 1
            correct = by_d["correct"]
            verif = by_d["total"] - by_d.get("unverifiable", 0)
            pct = f"{100 * correct / verif:.0f}%" if verif > 0 else "N/A"
            row.append(f"{correct}/{verif} ({pct})")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # 两两对比
    rank = {"correct": 2, "unverifiable": 1, "wrong": 0, "error": -1}
    if len(order) >= 2:
        # 对比第一组和最后一组
        pairs = []
        idx_list = [int(k) for k in order]
        if 0 in idx_list and 4 in idx_list:
            pairs.append(("0", "4"))  # 无few-shot vs 有few-shot
        if 1 in idx_list and 5 in idx_list:
            pairs.append(("1", "5"))  # 有知识无few-shot vs 有知识有few-shot

        for baseline, test in pairs:
            if baseline not in exps or test not in exps:
                continue
            b_label = exps[baseline]["label"]
            t_label = exps[test]["label"]
            lines.append(f"## [{test}] {t_label} vs [{baseline}] {b_label}")
            lines.append("")
            b_map = {r["id"]: r for r in exps[baseline]["details"]}
            t_map = {r["id"]: r for r in exps[test]["details"]}
            improved = [(qid, b_map[qid], t_map[qid]) for qid in sorted(b_map)
                         if rank.get(t_map[qid]["verdict"], 0) > rank.get(b_map[qid]["verdict"], 0)]
            degraded = [(qid, b_map[qid], t_map[qid]) for qid in sorted(b_map)
                         if rank.get(t_map[qid]["verdict"], 0) < rank.get(b_map[qid]["verdict"], 0)]
            lines.append(f"改善 {len(improved)} 题, 退步 {len(degraded)} 题, 净变化 {len(improved) - len(degraded):+d}")
            lines.append("")
            if improved:
                lines.append("### 改善")
                lines.append("| 题号 | 难度 | 变化 |")
                lines.append("|------|------|------|")
                for qid, b, t in improved:
                    lines.append(f"| {qid} | {b['difficulty']} | {b['verdict']} → {t['verdict']} |")
                lines.append("")
            if degraded:
                lines.append("### 退步")
                lines.append("| 题号 | 难度 | 变化 |")
                lines.append("|------|------|------|")
                for qid, b, t in degraded:
                    lines.append(f"| {qid} | {b['difficulty']} | {b['verdict']} → {t['verdict']} |")
                lines.append("")

    with open(report_path, "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    exp_indices = None
    if "--exp" in sys.argv:
        idx = sys.argv.index("--exp")
        exp_indices = [int(x) for x in sys.argv[idx + 1:]]
    elif len(sys.argv) > 1 and sys.argv[1] not in ("--help", "-h"):
        print("用法:")
        print("  python eval/scripts/run_eval.py                # 全部 6 组")
        print("  python eval/scripts/run_eval.py --exp 0 4 5    # 指定实验索引")
        sys.exit(1)

    run_eval(exp_indices)
