"""
批量调用 LLM 生成 SQL — 用于非 Claude Code 环境（如公司 Ubuntu + Qwen3 32B）

用法:
  # OpenAI 兼容 API（Qwen3 32B via vLLM/Ollama）
  python eval/scripts/generate_with_llm.py \
    --model openai/qwen3-32b \
    --api-base http://10.220.239.55:8000/v1 \
    --prompt-config E \
    --label "Qwen3-32B + Few-shot"

  # Ollama 本地模型
  python eval/scripts/generate_with_llm.py \
    --model ollama/qwen3:8b \
    --prompt-config E \
    --label "Qwen3-8B + Few-shot"

  # 指定题目范围（调试用）
  python eval/scripts/generate_with_llm.py \
    --model ollama/qwen3:8b \
    --prompt-config E \
    --label "test" \
    --range Q01-Q10

输入:
  .generated/prompts_{config_name}.json — 由 generate_sqls.py 生成的 prompt 文件

输出:
  results/all_sqls.json — 自动追加新实验组
"""

import json, sys, re, time, argparse
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
                            system: str, user: str) -> str:
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
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def call_ollama(model: str, system: str, user: str) -> str:
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
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data["message"]["content"]


def generate_sql(model: str, api_base: str, api_key: str,
                  user_prompt: str) -> str:
    """根据模型前缀选择调用方式"""
    if model.startswith("ollama/"):
        text = call_ollama(model, SYSTEM_PROMPT, user_prompt)
    else:
        text = call_openai_compatible(api_base, model, api_key, SYSTEM_PROMPT, user_prompt)
    return extract_sql(text)


def main():
    parser = argparse.ArgumentParser(description="批量调用 LLM 生成 SQL")
    parser.add_argument("--model", required=True, help="模型名 (如 openai/qwen3-32b, ollama/qwen3:8b)")
    parser.add_argument("--api-base", default="http://localhost:8000/v1", help="OpenAI 兼容 API 地址")
    parser.add_argument("--api-key", default="none", help="API key (Ollama 不需要)")
    parser.add_argument("--prompt-config", required=True, choices=list(CONFIG_NAMES.keys()), help="Prompt 配置 (A-F)")
    parser.add_argument("--label", required=True, help="实验标签（写入 all_sqls.json）")
    parser.add_argument("--range", default=None, help="题目范围 (如 Q01-Q10)，默认全部")
    args = parser.parse_args()

    # 加载 prompt
    config_name = CONFIG_NAMES[args.prompt_config]
    prompt_path = GENERATED_DIR / f"prompts_{config_name}.json"
    if not prompt_path.exists():
        print(f"ERROR: {prompt_path} not found. 先跑 python eval/scripts/generate_sqls.py")
        sys.exit(1)

    with open(prompt_path) as f:
        data = json.load(f)
    prompts = data["prompts"]

    # 题目范围过滤
    if args.range:
        m = re.match(r'Q(\d+)-Q(\d+)', args.range)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            prompts = {k: v for k, v in prompts.items()
                       if start <= int(k[1:]) <= end}

    print(f"Model: {args.model}")
    print(f"Config: {args.prompt_config} ({config_name})")
    print(f"Questions: {len(prompts)}")
    print()

    # 逐题生成
    results = {}
    for i, (qid, info) in enumerate(sorted(prompts.items()), 1):
        try:
            sql = generate_sql(args.model, args.api_base, args.api_key, info["user_prompt"])
            results[qid] = sql
            print(f"  {qid} ({i}/{len(prompts)}) ✓")
        except Exception as e:
            print(f"  {qid} ({i}/{len(prompts)}) ✗ {str(e)[:80]}")
            results[qid] = f"-- ERROR: {e}"
            time.sleep(2)

    # 追加到 all_sqls.json
    sqls_path = RESULTS_DIR / "all_sqls.json"
    with open(sqls_path) as f:
        all_data = json.load(f)

    model_short = args.model.split("/")[-1]
    all_data["experiments"].append({
        "label": args.label,
        "model": model_short,
        "schema": "full" if "fullschema" in config_name else "schemalink",
        "few_shot": "fewshot" in config_name,
        "knowledge": "knowledge" in config_name,
        "retrieval": data["_meta"].get("retrieval", ""),
        "generated_at": datetime.now().strftime("%Y-%m-%d"),
    })

    for qid in sorted(all_data["sqls"].keys()):
        all_data["sqls"][qid][args.label] = results.get(qid, "")

    with open(sqls_path, "w") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    success = sum(1 for v in results.values() if not v.startswith("-- ERROR"))
    print(f"\n完成: {success}/{len(results)} 成功")
    print(f"结果已追加到 {sqls_path}")
    print(f"实验索引: {len(all_data['experiments']) - 1}")
    print(f"\n下一步: python eval/scripts/run_eval.py --exp {len(all_data['experiments']) - 1}")


if __name__ == "__main__":
    main()
