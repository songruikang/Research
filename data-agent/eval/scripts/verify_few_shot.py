"""
验证 few-shot pairs 的 SQL 可执行性
用 DuckDB + mock 数据做 dry-run，标记 pass/fail
"""

import json
import duckdb
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def main():
    db_path = str(PROJECT_ROOT / "telecom" / "output" / "telecom_nms.duckdb")
    pairs_path = PROJECT_ROOT / "eval" / "few_shot_pairs.json"

    with open(pairs_path) as f:
        pairs = json.load(f)

    conn = duckdb.connect(db_path, read_only=True)

    results = []
    pass_count = 0
    fail_count = 0

    for pair in pairs:
        pid = pair["id"]
        sql = pair["sql"]
        try:
            result = conn.execute(sql)
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            row_count = len(rows)
            results.append({
                **pair,
                "status": "pass",
                "row_count": row_count,
                "columns": columns
            })
            status_icon = "✓" if row_count > 0 else "⚠"
            print(f"  {status_icon} {pid}: pass ({row_count} rows) — {pair['question'][:40]}")
            pass_count += 1
        except Exception as e:
            error_msg = str(e)
            results.append({
                **pair,
                "status": "fail",
                "error": error_msg
            })
            print(f"  ✗ {pid}: FAIL — {error_msg[:80]}")
            fail_count += 1

    conn.close()

    # 写出带标记的结果
    output_path = PROJECT_ROOT / "eval" / "few_shot_verified.json"
    with open(output_path, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 汇总
    print(f"\n{'='*60}")
    print(f"总计: {len(pairs)} | 通过: {pass_count} | 失败: {fail_count}")
    print(f"通过率: {pass_count/len(pairs)*100:.0f}%")

    zero_row = sum(1 for r in results if r.get("status") == "pass" and r.get("row_count", 0) == 0)
    if zero_row:
        print(f"⚠ 返回 0 行: {zero_row} 条（SQL 正确但 mock 数据不匹配）")

    print(f"\n结果已写入: {output_path}")

    # 输出 fail 的详细信息
    failed = [r for r in results if r["status"] == "fail"]
    if failed:
        print(f"\n{'='*60}")
        print("失败详情:\n")
        for r in failed:
            print(f"[{r['id']}] {r['question']}")
            print(f"  SQL: {r['sql'][:120]}")
            print(f"  Error: {r['error']}")
            print()


if __name__ == "__main__":
    main()
