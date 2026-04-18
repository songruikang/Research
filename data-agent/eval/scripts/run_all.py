"""
一键评测全部实验 — 生成 prompt + 评测已有 SQL + 输出报告

用法:
  python eval/scripts/run_all.py              # 评测 all_sqls.json 中所有实验
  python eval/scripts/run_all.py --regen      # 先重新生成 prompt 再评测
  python eval/scripts/run_all.py --exp 0 4 8  # 只评测指定实验

流程:
  1. [可选] 重新生成 .generated/prompts_*.json
  2. 加载 results/all_sqls.json 中所有实验
  3. 逐组评测，输出终端报告
  4. 保存详细结果到 .generated/eval_results_{timestamp}.json
  5. 保存 MD 报告到 results/report_{timestamp}.md
"""

import sys, subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent


def main():
    args = sys.argv[1:]

    # 是否重新生成 prompt
    if "--regen" in args:
        args.remove("--regen")
        print("=" * 60)
        print("Step 1: 重新生成 prompt")
        print("=" * 60)
        subprocess.run([sys.executable, str(SCRIPTS_DIR / "generate_sqls.py")], check=True)
        print()

    # 传递剩余参数给 run_eval.py
    print("=" * 60)
    print("Step 2: 评测 + 报告")
    print("=" * 60)
    cmd = [sys.executable, str(SCRIPTS_DIR / "run_eval.py")] + args
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
