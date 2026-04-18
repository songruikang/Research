"""
批量调用 LLM 生成 SQL — 用于非 Claude Code 环境（如公司 Ubuntu + Qwen3 32B）

用法:
  # 全量跑 6 组配置（挂机模式，适合过夜）
  python eval/scripts/generate_sqls.py \
    --model openai/qwen3-32b \
    --api-base http://10.220.239.55:8000/v1 \
    --all

  # 只跑指定配置
  python eval/scripts/generate_sqls.py \
    --model openai/qwen3-32b \
    --api-base http://10.220.239.55:8000/v1 \
    --prompt-config E

  # Ollama 本地模型
  python eval/scripts/generate_sqls.py \
    --model ollama/qwen3:8b \
    --prompt-config E

  # 调试：只跑 10 题
  python eval/scripts/generate_sqls.py \
    --model ollama/qwen3:8b \
    --prompt-config E \
    --range Q01-Q10

输入:
  .generated/prompts_{config}.json — 由 generate_prompts.py 生成

输出:
  results/all_sqls.json — 自动追加新实验组
  .generated/progress_{model}_{config}.json — 断点续跑进度文件
"""

import json, sys, re, time, argparse, traceback
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EVAL_DIR = PROJECT_ROOT / "eval"
RESULTS_DIR = EVAL_DIR / "results"
GENERATED_DIR = EVAL_DIR / ".generated"

CONFIG_NAMES = {
    "A": "fullschema_no_knowledge",
    "B": "fullschema_with_knowledge",
    "C": "schemalink_no_knowledge",
    "D": "schemalink_with_knowledge",
    "E": "fullschema_fewshot",
    "F": "fullschema_fewshot_knowledge",
}

CONFIG_LABELS = {
    "A": "全量Schema 无知识",
    "B": "全量Schema 有知识",
    "C": "Schema Linking 无知识",
    "D": "Schema Linking 有知识",
    "E": "全量Schema + Few-shot",
    "F": "全量Schema + Few-shot + 知识",
}

SYSTEM_PROMPT = """你是一个电信网络管理系统的 SQL 专家。根据给定的数据库 Schema 和用户问题，生成一条精确的 SQL 查询语句。

要求：
- 只输出一条 SQL，不要解释
- 使用标准 SQL 语法
- 表名和列名严格按 Schema 中的定义
- 适当使用 ORDER BY 使结果有意义
- 浮点数用 ROUND() 保留合理精度
- 不要用 SELECT *，明确列出需要的列"""


def extract_sql(text: str) -> str:
    """从 LLM 回复中提取 SQL"""
    m = re.search(r'```sql\s*(.*?)```', text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r'```\s*(.*?)```', text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


def call_openai_compatible(api_base: str, model: str, api_key: str,
                            system: str, user: str, timeout: int = 120) -> str:
    """调用 OpenAI 兼容 API"""
    import urllib.request
    url = f"{api_base.rstrip('/')}/chat/completions"
    payload = {
        "model": model.split("/", 1)[-1] if "/" in model else model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 2000,
        "temperature": 0,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def call_ollama(model: str, system: str, user: str, timeout: int = 120) -> str:
    """调用 Ollama API"""
    import urllib.request
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": model.split("/", 1)[-1] if "/" in model else model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return data["message"]["content"]


def generate_sql(model: str, api_base: str, api_key: str,
                  user_prompt: str, timeout: int = 120) -> str:
    """根据模型前缀选择调用方式"""
    if model.startswith("ollama/"):
        text = call_ollama(model, SYSTEM_PROMPT, user_prompt, timeout)
    else:
        text = call_openai_compatible(api_base, model, api_key, SYSTEM_PROMPT, user_prompt, timeout)
    return extract_sql(text)


def run_config(model: str, api_base: str, api_key: str, config: str,
               timeout: int, max_retries: int, q_range: tuple | None = None) -> dict:
    """运行一个配置的全部题目，支持断点续跑"""
    config_name = CONFIG_NAMES[config]
    prompt_path = GENERATED_DIR / f"prompts_{config_name}.json"
    if not prompt_path.exists():
        print(f"  [SKIP] {prompt_path.name} not found")
        return {}

    with open(prompt_path) as f:
        data = json.load(f)
    prompts = data["prompts"]

    # 题目范围过滤
    if q_range:
        start, end = q_range
        prompts = {k: v for k, v in prompts.items()
                   if start <= int(k[1:]) <= end}

    # 断点续跑：加载进度
    model_short = model.split("/")[-1].replace(":", "_")
    progress_path = GENERATED_DIR / f"progress_{model_short}_{config}.json"
    done = {}
    if progress_path.exists():
        with open(progress_path) as f:
            done = json.load(f)
        print(f"  从断点恢复: {len(done)} 题已完成")

    # 统计
    total = len(prompts)
    skipped = sum(1 for qid in prompts if qid in done)
    success = sum(1 for v in done.values() if not v.startswith("-- ERROR"))
    errors = []
    start_time = time.time()
    completed_this_run = 0

    for i, (qid, info) in enumerate(sorted(prompts.items()), 1):
        if qid in done:
            continue

        retries = 0
        while retries <= max_retries:
            try:
                t0 = time.time()
                sql = generate_sql(model, api_base, api_key, info["user_prompt"], timeout)
                elapsed = time.time() - t0
                done[qid] = sql
                success += 1
                completed_this_run += 1

                # 进度 + 预估剩余时间
                remaining = total - i
                avg_time = (time.time() - start_time) / completed_this_run
                eta_min = remaining * avg_time / 60
                print(f"  {qid} ({i}/{total}) ✓ {elapsed:.1f}s | 剩余 ~{eta_min:.0f}min")
                break
            except Exception as e:
                retries += 1
                err_msg = str(e)[:100]
                if retries <= max_retries:
                    wait = min(retries * 5, 30)
                    print(f"  {qid} ({i}/{total}) 重试 {retries}/{max_retries} (等待{wait}s) — {err_msg}")
                    time.sleep(wait)
                else:
                    done[qid] = f"-- ERROR: {e}"
                    errors.append({"qid": qid, "error": err_msg})
                    completed_this_run += 1
                    print(f"  {qid} ({i}/{total}) ✗ 放弃 — {err_msg}")

        # 每题保存进度
        with open(progress_path, "w") as f:
            json.dump(done, f, ensure_ascii=False, indent=2)

    # 完成后删除进度文件
    if progress_path.exists():
        progress_path.unlink()

    return {"results": done, "errors": errors, "success": success, "total": total}


def save_to_all_sqls(results: dict, model: str, config: str, label: str):
    """追加结果到 all_sqls.json"""
    sqls_path = RESULTS_DIR / "all_sqls.json"
    with open(sqls_path) as f:
        all_data = json.load(f)

    config_name = CONFIG_NAMES[config]
    model_short = model.split("/")[-1]
    all_data["experiments"].append({
        "label": label,
        "model": model_short,
        "schema": "full" if "fullschema" in config_name else "schemalink",
        "few_shot": "fewshot" in config_name,
        "knowledge": "knowledge" in config_name,
        "generated_at": datetime.now().strftime("%Y-%m-%d"),
    })

    for qid in sorted(all_data["sqls"].keys()):
        all_data["sqls"][qid][label] = results.get(qid, "")

    with open(sqls_path, "w") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    return len(all_data["experiments"]) - 1


def main():
    parser = argparse.ArgumentParser(description="批量调用 LLM 生成 SQL")
    parser.add_argument("--model", required=True, help="模型名 (如 openai/qwen3-32b, ollama/qwen3:8b)")
    parser.add_argument("--api-base", default="http://localhost:8000/v1", help="OpenAI 兼容 API 地址")
    parser.add_argument("--api-key", default="none", help="API key")
    parser.add_argument("--all", action="store_true", help="全量跑 6 组配置 (A-F)")
    parser.add_argument("--prompt-config", choices=list(CONFIG_NAMES.keys()), help="Prompt 配置 (A-F)")
    parser.add_argument("--label", default=None, help="实验标签（--all 模式自动生成）")
    parser.add_argument("--range", default=None, help="题目范围 (如 Q01-Q10)")
    parser.add_argument("--timeout", type=int, default=120, help="单题超时秒数 (默认 120)")
    parser.add_argument("--max-retries", type=int, default=3, help="单题最大重试次数 (默认 3)")
    args = parser.parse_args()

    if not args.all and not args.prompt_config:
        parser.error("必须指定 --all 或 --prompt-config")

    # 解析题目范围
    q_range = None
    if args.range:
        m = re.match(r'Q(\d+)-Q(\d+)', args.range)
        if m:
            q_range = (int(m.group(1)), int(m.group(2)))

    # 确定要跑的配置
    configs = list(CONFIG_NAMES.keys()) if args.all else [args.prompt_config]
    model_short = args.model.split("/")[-1]

    total_questions = len(configs) * 100
    print(f"{'=' * 60}")
    print(f"模型: {args.model}")
    print(f"配置: {', '.join(configs)} ({len(configs)} 组 × 100 题 = {total_questions} 次调用)")
    print(f"超时: {args.timeout}s/题, 重试: {args.max_retries}次")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=' * 60}")

    all_errors = []
    exp_indices = []

    for config in configs:
        label = args.label if args.label else f"{model_short} {CONFIG_LABELS[config]}"

        print(f"\n{'─' * 60}")
        print(f"[{config}] {label}")
        print(f"{'─' * 60}")

        t_start = time.time()
        result = run_config(args.model, args.api_base, args.api_key,
                            config, args.timeout, args.max_retries, q_range)
        if not result:
            continue

        elapsed_min = (time.time() - t_start) / 60
        exp_idx = save_to_all_sqls(result["results"], args.model, config, label)
        exp_indices.append(exp_idx)

        print(f"  成功: {result['success']}/{result['total']} | 耗时: {elapsed_min:.1f}min")
        if result["errors"]:
            print(f"  失败: {len(result['errors'])} 题")
            all_errors.extend(result["errors"])

    # 汇总
    print(f"\n{'=' * 60}")
    print(f"全部完成: {len(exp_indices)} 组实验")
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if all_errors:
        print(f"\n失败记录 ({len(all_errors)} 题):")
        for e in all_errors:
            print(f"  {e['qid']}: {e['error']}")
    if exp_indices:
        idx_str = " ".join(str(i) for i in exp_indices)
        print(f"\n下一步: python eval/scripts/run_eval.py --exp {idx_str}")


if __name__ == "__main__":
    main()
