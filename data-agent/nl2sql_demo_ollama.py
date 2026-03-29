import json
import urllib.request
import duckdb

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:8b"

def call_ollama(system: str, user: str) -> str:
    payload = json.dumps({
        "model": MODEL,
        "stream": False,
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())["message"]["content"].strip()
    if "</think>" in result:
        result = result.split("</think>")[-1].strip()
    for tag in ["```sql", "```"]:
        result = result.replace(tag, "")
    return result.strip()

# ── 1. 建样本数据库 ──────────────────────────────────────────────
con = duckdb.connect()
con.execute("""
    CREATE TABLE orders (
        order_id    INTEGER,
        customer    VARCHAR,
        product     VARCHAR,
        category    VARCHAR,
        amount      DECIMAL(10,2),
        order_date  DATE
    )
""")
con.execute("""
    INSERT INTO orders VALUES
        (1,  'Alice',   'MacBook Pro',   'Electronics', 12999.00, '2024-01-15'),
        (2,  'Bob',     'iPhone 15',     'Electronics',  7999.00, '2024-01-20'),
        (3,  'Alice',   'AirPods Pro',   'Electronics',  1799.00, '2024-02-03'),
        (4,  'Charlie', 'Desk Chair',    'Furniture',    2499.00, '2024-02-10'),
        (5,  'Bob',     'Standing Desk', 'Furniture',    4999.00, '2024-02-15'),
        (6,  'Diana',   'iPad Air',      'Electronics',  4799.00, '2024-03-01'),
        (7,  'Alice',   'Monitor',       'Electronics',  3299.00, '2024-03-05'),
        (8,  'Charlie', 'Keyboard',      'Electronics',   899.00, '2024-03-10'),
        (9,  'Diana',   'Bookshelf',     'Furniture',    1299.00, '2024-03-20'),
        (10, 'Bob',     'Webcam',        'Electronics',   599.00, '2024-03-25')
""")

# ── 2. 获取表结构 ────────────────────────────────────────────────
def get_schema():
    result = con.execute("DESCRIBE orders").fetchall()
    cols = ", ".join(f"{row[0]} {row[1]}" for row in result)
    return f"Table: orders({cols})"

# ── 3. NL → SQL ──────────────────────────────────────────────────
def nl_to_sql(question: str) -> str:
    return call_ollama(
        system=f"""你是一个 NL2SQL 专家。根据用户问题生成 DuckDB SQL 查询。
数据库结构：{get_schema()}
只返回 SQL 语句本身，不要任何解释，不要 markdown 代码块。""",
        user=question
    )

# ── 4. 执行并展示结果 ─────────────────────────────────────────────
def ask(question: str):
    print(f"\n{'='*55}")
    print(f"问题: {question}")
    sql = nl_to_sql(question)
    print(f"SQL:  {sql}")
    print("-"*55)
    rows = con.execute(sql).fetchall()
    cols = [d[0] for d in con.execute(sql).description]
    print("  ".join(f"{c:<15}" for c in cols))
    print("-"*55)
    for row in rows:
        print("  ".join(f"{str(v):<15}" for v in row))

# ── 5. 测试问题 ───────────────────────────────────────────────────
if __name__ == "__main__":
    questions = [
        "每个客户的总消费金额是多少？按金额从高到低排列",
        "哪个品类的销售额最高？",
        "2024年2月有哪些订单？",
        "买过超过两件商品的客户有哪些？",
    ]
    for q in questions:
        ask(q)
