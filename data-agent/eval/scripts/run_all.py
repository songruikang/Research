"""
一键全流程：生成 Prompt → 调 LLM 生成 SQL → 评测出报告

用法:
  # 完整流程（公司环境，Qwen3 32B）
  python eval/scripts/run_all.py \
    --model ollama_chat/qwen3:32b \
    --api-base http://10.220.239.55:11434/v1

  # 只重新评测已有的 all_sqls.json（不调模型）
  python eval/scripts/run_all.py

  # 只评测指定实验
  python eval/scripts/run_all.py --exp 0 4

参数:
  --model MODEL        LLM 模型名（指定后会执行 Step 2 生成 SQL）
  --api-base URL       模型 API 地址
  --api-key KEY        API key（Ollama 不需要）
  --prompt-config X    只跑指定 Prompt 配置（默认 --all 全部 6 组）
  --exp N [N ...]      只评测指定实验索引
  --timeout N          单题超时秒数（默认 120）
  --max-retries N      单题最大重试次数（默认 3）

流程:
  Step 1: generate_prompts.py → .generated/prompts_*.json (6组)
  Step 2: generate_sqls.py    → results/all_sqls.json (调 LLM，仅 --model 时执行)
  Step 3: run_eval.py         → results/report_*.md
"""

import sys, subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent


def main():
    args = sys.argv[1:]

    # 解析是否有模型参数（决定是否跑 Step 2）
    has_model = "--model" in args

    # 分离 run_eval 专用参数（--exp）和 generate_sqls 参数
    eval_args = []
    gen_args = []
    i = 0
    while i < len(args):
        if args[i] == "--exp":
            # --exp 及其后续数字归 eval
            eval_args.append(args[i])
            i += 1
            while i < len(args) and not args[i].startswith("--"):
                eval_args.append(args[i])
                i += 1
        else:
            gen_args.append(args[i])
            i += 1

    # Step 1: 生成 Prompt
    print("=" * 60)
    print("Step 1: 生成 6 组 Prompt 文件")
    print("=" * 60)
    subprocess.run([sys.executable, str(SCRIPTS_DIR / "generate_prompts.py")], check=True)
    print()

    # Step 2: 调 LLM 生成 SQL（仅当指定了 --model 时）
    if has_model:
        print("=" * 60)
        print("Step 2: 调 LLM 生成 SQL")
        print("=" * 60)
        cmd = [sys.executable, str(SCRIPTS_DIR / "generate_sqls.py")]
        # 如果没有指定 --prompt-config，默认 --all
        if "--prompt-config" not in gen_args and "--all" not in gen_args:
            gen_args.append("--all")
        cmd.extend(gen_args)
        subprocess.run(cmd, check=True)
        print()

    # Step 3: 评测 + 报告
    print("=" * 60)
    print(f"Step 3: 评测 + 报告")
    print("=" * 60)
    cmd = [sys.executable, str(SCRIPTS_DIR / "run_eval.py")] + eval_args
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
