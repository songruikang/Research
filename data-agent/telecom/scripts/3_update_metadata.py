#!/usr/bin/env python3
"""
WrenAI 电信NMS元数据导入脚本

从 telecom_mdl.json 读取语义层定义，直接写入 WrenAI 的 SQLite 数据库。
覆盖: model(中文描述), model_column(displayName/PK/type等), relation(中文名)

前提:
  1. WrenAI Docker 已启动，且已通过 UI 连接 DuckDB 并导入了14张表并 Deploy 成功
  2. docker-compose 使用 bind mount 模式（db 文件在宿主机 docker/data/ 下）

使用:
  python3 telecom/scripts/3_update_metadata.py
"""
import json
import os
import sqlite3
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TELECOM_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_ROOT = os.path.dirname(TELECOM_DIR)
MDL_PATH = os.path.join(TELECOM_DIR, "input", "telecom_mdl.json")

# bind mount 模式：db 直接在宿主机上，不需要 docker cp
HOST_DB = os.environ.get(
    "WREN_UI_SQLITE_PATH",
    os.path.join(PROJECT_ROOT, "WrenAI", "docker", "data", "db.sqlite3"),
)

CONTAINER = os.environ.get("WREN_UI_CONTAINER", "wrenai-wren-ui-1")
GRAPHQL_URL = os.environ.get("WREN_GRAPHQL_URL", "http://localhost:3000/api/graphql")


def run(cmd, check=True):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and r.returncode != 0:
        print(f"ERROR: {cmd}\n{r.stderr}")
        sys.exit(1)
    return r


def step(msg):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")


# ---------------------------------------------------------------------------
# Step 0: 加载 MDL
# ---------------------------------------------------------------------------
step("0. 加载 telecom_mdl.json")
with open(MDL_PATH) as f:
    mdl = json.load(f)
print(f"  模型: {len(mdl['models'])} 个")
print(f"  关系: {len(mdl.get('relationships', []))} 条")
total_cols = sum(len(m.get("columns", [])) for m in mdl["models"])
print(f"  字段: {total_cols} 个")

# ---------------------------------------------------------------------------
# Step 1: 打开宿主机上的 SQLite（bind mount，无需 docker cp）
# ---------------------------------------------------------------------------
step("1. 停止容器 + 打开 SQLite")

# 先停容器，避免并发写入冲突
print(f"  停止 {CONTAINER} ...")
run(f"docker stop {CONTAINER}", check=False)

print(f"  路径: {HOST_DB}")
if not os.path.exists(HOST_DB):
    print(f"  ✗ 文件不存在: {HOST_DB}")
    print(f"  请确认 WrenAI Docker 已启动且已完成数据源配置")
    sys.exit(1)

file_size = os.path.getsize(HOST_DB)
print(f"  文件大小: {file_size:,} bytes")

for suffix in ["-wal", "-shm"]:
    wal_path = HOST_DB + suffix
    if os.path.exists(wal_path):
        print(f"  {suffix} 文件: {os.path.getsize(wal_path):,} bytes")

conn = sqlite3.connect(HOST_DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# WAL checkpoint：确保 -wal 数据刷回主文件
c.execute("PRAGMA wal_checkpoint(TRUNCATE)")

# 完整性检查
integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
if integrity != "ok":
    print(f"  ✗ 数据库损坏: {integrity}")
    print(f"  请删除 {HOST_DB} 并重新导入")
    conn.close()
    sys.exit(1)
print(f"  完整性: ok")

journal = c.execute("PRAGMA journal_mode").fetchone()[0]
print(f"  journal_mode: {journal}")

# ---------------------------------------------------------------------------
# Step 2: 更新模型 + 字段元数据
# ---------------------------------------------------------------------------
step("2. 更新模型和字段元数据")

# 前置检查
tables = [r[0] for r in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()]
if "model" not in tables:
    print(f"  ✗ SQLite 中没有 model 表（现有表: {tables}）")
    print(f"  请确认 WrenAI UI 已完成数据源配置和 Deploy")
    conn.close()
    sys.exit(1)

# 建立映射: table_name → model_id
model_map = {}
for row in c.execute("SELECT id, source_table_name FROM model"):
    model_map[row["source_table_name"]] = row["id"]

if not model_map:
    print(f"  ✗ model 表有 0 行数据")
    print(f"  请确认 WrenAI UI 已完成 Deploy（Modeling 页面不再转圈）")
    conn.close()
    sys.exit(1)

# 建立映射: (model_id, col_name) → column_id
col_map = {}
for row in c.execute("SELECT id, model_id, source_column_name FROM model_column"):
    col_map[(row["model_id"], row["source_column_name"])] = row["id"]

print(f"  SQLite 现有: {len(model_map)} 模型, {len(col_map)} 字段")

model_ok, col_ok, col_warn = 0, 0, []

for mdl_model in mdl["models"]:
    tname = mdl_model["name"]
    mid = model_map.get(tname)
    if not mid:
        print(f"  ⚠ 模型 {tname} 在 SQLite 中不存在，跳过")
        continue

    # --- 更新 model ---
    mdl_props = mdl_model.get("properties", {})
    model_desc = mdl_props.get("description", "")
    model_display = mdl_props.get("displayName", tname)

    existing_props = json.loads(
        c.execute("SELECT properties FROM model WHERE id=?", (mid,)).fetchone()[0]
    )
    existing_props["description"] = model_desc
    existing_props["displayName"] = model_display

    c.execute(
        "UPDATE model SET display_name=?, properties=? WHERE id=?",
        (model_display, json.dumps(existing_props, ensure_ascii=False), mid),
    )
    model_ok += 1

    # --- 更新 columns ---
    pk_col = mdl_model.get("primaryKey", "")

    for mdl_col in mdl_model.get("columns", []):
        cname = mdl_col["name"]
        cid = col_map.get((mid, cname))
        if not cid:
            col_warn.append(f"{tname}.{cname}")
            continue

        col_props = mdl_col.get("properties", {})
        display_name = col_props.get("displayName", cname)
        description = col_props.get("description", "")
        is_calculated = 1 if mdl_col.get("isCalculated", False) else 0
        is_pk = 1 if cname == pk_col else 0
        not_null = 1 if mdl_col.get("notNull", False) else 0
        col_type = mdl_col.get("type", "VARCHAR")

        new_props = json.dumps(
            {"description": description, "displayName": display_name},
            ensure_ascii=False,
        )

        c.execute(
            """UPDATE model_column
               SET display_name=?, is_calculated=?, is_pk=?, not_null=?, type=?, properties=?
               WHERE id=?""",
            (display_name, is_calculated, is_pk, not_null, col_type, new_props, cid),
        )
        col_ok += 1

print(f"  模型更新: {model_ok}/{len(mdl['models'])}")
print(f"  字段更新: {col_ok}/{total_cols}")
if col_warn:
    print(f"  ⚠ 未匹配字段: {col_warn}")

# ---------------------------------------------------------------------------
# Step 3: 更新关系 (名称 + 中文描述)
# ---------------------------------------------------------------------------
step("3. 更新关系名称和中文描述")

# 重建映射
full_col_map = {}
for row in c.execute("SELECT id, model_id, source_column_name FROM model_column"):
    full_col_map[(row["model_id"], row["source_column_name"])] = row["id"]

name_to_mid = {}
for row in c.execute("SELECT id, source_table_name FROM model"):
    name_to_mid[row["source_table_name"]] = row["id"]

# 删除旧关系
old_count = c.execute("SELECT COUNT(*) FROM relation").fetchone()[0]
c.execute("DELETE FROM relation")
print(f"  删除旧关系: {old_count} 条")

# 获取 project_id
project_id = c.execute("SELECT project_id FROM model LIMIT 1").fetchone()[0]

rel_ok, rel_fail = 0, []
for mdl_rel in mdl.get("relationships", []):
    models = mdl_rel["models"]
    from_table, to_table = models[0], models[1]
    condition = mdl_rel["condition"]

    parts = condition.split("=")
    from_col = parts[0].strip().split(".")[-1]
    to_col = parts[1].strip().split(".")[-1]

    from_mid = name_to_mid.get(from_table)
    to_mid = name_to_mid.get(to_table)
    if not from_mid or not to_mid:
        rel_fail.append(f"{mdl_rel['name']}: model not found")
        continue

    from_cid = full_col_map.get((from_mid, from_col))
    to_cid = full_col_map.get((to_mid, to_col))
    if not from_cid or not to_cid:
        rel_fail.append(
            f"{mdl_rel['name']}: column not found "
            f"({from_table}.{from_col} -> {to_table}.{to_col})"
        )
        continue

    rel_props = mdl_rel.get("properties", {})
    rel_display = rel_props.get("displayName", mdl_rel["name"])
    rel_desc = rel_props.get("description", "")
    props_json = json.dumps(
        {"displayName": rel_display, "description": rel_desc},
        ensure_ascii=False,
    ) if rel_props else None

    c.execute(
        """INSERT INTO relation
           (project_id, name, join_type, from_column_id, to_column_id, properties)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (project_id, rel_display, mdl_rel["joinType"], from_cid, to_cid, props_json),
    )
    rel_ok += 1

print(f"  插入新关系: {rel_ok}/{len(mdl.get('relationships', []))}")
if rel_fail:
    print(f"  ⚠ 失败: {rel_fail}")

conn.commit()
conn.close()
print(f"  已写入 {HOST_DB}")

# ---------------------------------------------------------------------------
# Step 4: 重启 wren-ui + 部署
# ---------------------------------------------------------------------------
step("4. 启动 wren-ui 使元数据生效")

run(f"docker start {CONTAINER}")
print("  已重启 wren-ui，等待启动...")
time.sleep(12)

for i in range(20):
    r = run(
        f"curl -s -o /dev/null -w '%{{http_code}}' {GRAPHQL_URL}",
        check=False,
    )
    code = r.stdout.strip().replace("'", "")
    if code in ("200", "400"):
        print(f"  wren-ui 已就绪 (HTTP {code})")
        break
    print(f"  等待中... ({i+1}/20, HTTP {code})")
    time.sleep(3)
else:
    print("  ⚠ wren-ui 未能在60秒内就绪")
    sys.exit(1)

step("5. 触发 MDL 部署")
print("  正在部署（本地模型可能需要几分钟）...")
r = run(
    f'curl -s --max-time 300 -X POST {GRAPHQL_URL} '
    f'-H "Content-Type: application/json" '
    f"""-d '{{"query":"mutation {{ deploy(force: true) }}"}}'""",
    check=False,
)
if r.returncode == 0 and r.stdout:
    try:
        result = json.loads(r.stdout)
        if "errors" in result:
            msg = result["errors"][0].get("message", str(result["errors"]))
            print(f"  部署返回错误: {msg}")
            print(f"  请在 UI 的 Modeling 页面手动点击 Deploy")
        elif result.get("data"):
            print(f"  部署已触发")
        else:
            print(f"  响应: {r.stdout[:200]}")
    except json.JSONDecodeError:
        print(f"  响应解析失败: {r.stdout[:200]}")
else:
    print(f"  部署请求超时或失败，请在 UI 手动 Deploy")

# ---------------------------------------------------------------------------
# Step 6: 验证
# ---------------------------------------------------------------------------
step("6. 验证")

test_sql = (
    "SELECT ne.ne_id, ne.ne_name, ne.vendor, s.site_name "
    "FROM t_network_element ne "
    "JOIN t_site s ON ne.site_id = s.site_id LIMIT 3"
)
r = run(
    f'curl -s -X POST {GRAPHQL_URL} '
    f'-H "Content-Type: application/json" '
    f"""-d '{{"query":"mutation Preview($w: PreviewSQLDataInput!) """
    f"""{{ previewSql(data: $w) }}","variables":{{"w":{{"sql":"{test_sql}","limit":3}}}}}}' """,
    check=False,
)
if r.returncode == 0 and r.stdout:
    try:
        result = json.loads(r.stdout)
        if "errors" in result:
            print(f"  ⚠ SQL 执行失败: {result['errors'][0].get('message', '')}")
        else:
            data = result.get("data", {}).get("previewSql", {}).get("data", [])
            print(f"  JOIN 查询成功，返回 {len(data)} 行")
    except json.JSONDecodeError:
        print(f"  响应解析失败")
else:
    print(f"  验证请求失败")

# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
step("完成")
print(f"""
  模型: {model_ok} 个 (含中文表描述)
  字段: {col_ok} 个 (含 displayName / 中文描述 / PK / NOT NULL / type)
  关系: {rel_ok} 条 (含中文名称和描述)
  DB:   {HOST_DB}
""")
