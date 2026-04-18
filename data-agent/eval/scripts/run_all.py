"""
一键评测（组合调用 generate_sqls.py + run_eval.py）

用法:
  python eval/scripts/run_all.py              # 评测 all_sqls.json 中所有实验
  python eval/scripts/run_all.py --regen      # 先重新生成 6 组 prompt 再评测
  python eval/scripts/run_all.py --exp 0 4 8  # 只评测指定实验

参数:
  --regen            先跑 generate_sqls.py 重新生成 prompt 文件
  --exp N [N ...]    传递给 run_eval.py，指定评测哪些实验

输入/输出: 同 generate_sqls.py 和 run_eval.py
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
