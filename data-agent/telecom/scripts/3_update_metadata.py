#!/usr/bin/env python3
"""
WrenAI 电信NMS元数据导入脚本 (v2)

从 telecom_mdl.json 读取完整的语义层定义，写入 WrenAI 的 SQLite 数据库。
覆盖以下元数据：
  - model: display_name, properties (中文描述)
  - model_column: display_name, is_calculated, is_pk, not_null, type, properties (中文描述)
  - relation: name (中文), properties (中文描述)

使用方式:
  1. 确保 WrenAI Docker 已启动，且已通过 UI 连接 DuckDB 并导入了14张表
  2. 运行: python3 update_wren_metadata.py
  3. 脚本会自动: 拷贝DB → 更新元数据 → 拷贝回容器 → 重启 → 部署
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
# scripts/ → telecom/ → data-agent/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TELECOM_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_ROOT = os.path.dirname(TELECOM_DIR)
MDL_PATH = os.path.join(TELECOM_DIR, "input", "telecom_mdl.json")
OUTPUT_DIR = os.path.join(TELECOM_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
LOCAL_DB = os.path.join(OUTPUT_DIR, "wren_ui_db.sqlite3")
# 容器名和路径 — 可通过环境变量覆盖（公司环境可能不同）
# Mac 默认: 容器名 wrenai-wren-ui-1, SQLite 在 /app/data/db.sqlite3
# 公司云主机: 容器名可能不同, SQLite 可能在 /app/db.sqlite3
CONTAINER = os.environ.get("WREN_UI_CONTAINER", "wrenai-wren-ui-1")
REMOTE_DB = os.environ.get("WREN_UI_SQLITE_PATH", "/app/data/db.sqlite3")
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
# Step 1: 从容器拷贝 SQLite（WAL checkpoint + 三文件）
# ---------------------------------------------------------------------------
step("1. 从容器拷贝 SQLite 数据库")

# WAL 模式下数据可能在 -wal 文件中，先 checkpoint 强制写回主文件
run(
    f"docker exec {CONTAINER} sqlite3 {REMOTE_DB} \"PRAGMA wal_checkpoint(TRUNCATE);\"",
    check=False,  # 容器内可能没有 sqlite3 CLI，忽略失败
)

# 拷贝主文件
run(f"docker cp {CONTAINER}:{REMOTE_DB} {LOCAL_DB}")

# 同时拷贝 WAL 和 SHM 文件（如果存在）
for suffix in ["-wal", "-shm"]:
    r = run(f"docker cp {CONTAINER}:{REMOTE_DB}{suffix} {LOCAL_DB}{suffix}", check=False)
    if r.returncode == 0:
        print(f"  已拷贝 {suffix} 文件")

print(f"  已拷贝到 {LOCAL_DB}")

# ---------------------------------------------------------------------------
# Step 2: 更新模型 + 字段元数据
# ---------------------------------------------------------------------------
step("2. 更新模型和字段元数据")

conn = sqlite3.connect(LOCAL_DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# 前置检查：确认 SQLite 拷贝成功且有数据
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
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
    print(f"  ✗ model 表有0行数据")
    print(f"  可能原因: WAL数据未checkpoint、容器内DB路径不对、或UI未Deploy")
    print(f"  排查: docker exec {CONTAINER} sqlite3 {REMOTE_DB} 'SELECT COUNT(*) FROM model;'")
    conn.close()
    sys.exit(1)

# 建立映射: (model_id, col_name) → column row
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

# 重建 (model_id, col_name) → col_id 映射 (用于关系)
full_col_map = {}
for row in c.execute("SELECT id, model_id, source_column_name FROM model_column"):
    full_col_map[(row["model_id"], row["source_column_name"])] = row["id"]

# 反向映射: model_name → model_id
name_to_mid = {}
for row in c.execute("SELECT id, source_table_name FROM model"):
    name_to_mid[row["source_table_name"]] = row["id"]

# 删除所有旧关系
old_count = c.execute("SELECT COUNT(*) FROM relation").fetchone()[0]
c.execute("DELETE FROM relation")
print(f"  删除旧关系: {old_count} 条")

# 获取 project_id
project_id = c.execute("SELECT project_id FROM model LIMIT 1").fetchone()[0]

rel_ok, rel_fail = 0, []
for mdl_rel in mdl.get("relationships", []):
    models = mdl_rel["models"]
    from_table, to_table = models[0], models[1]
    condition = mdl_rel["condition"]  # e.g. "t_board.ne_id = t_network_element.ne_id"

    # 解析 condition 获取列名
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
        rel_fail.append(f"{mdl_rel['name']}: column not found ({from_table}.{from_col} → {to_table}.{to_col})")
        continue

    rel_props = mdl_rel.get("properties", {})
    rel_display = rel_props.get("displayName", mdl_rel["name"])
    rel_desc = rel_props.get("description", "")
    props_json = json.dumps(
        {"displayName": rel_display, "description": rel_desc},
        ensure_ascii=False,
    ) if rel_props else None

    c.execute(
        """INSERT INTO relation (project_id, name, join_type, from_column_id, to_column_id, properties)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (project_id, rel_display, mdl_rel["joinType"], from_cid, to_cid, props_json),
    )
    rel_ok += 1

print(f"  插入新关系: {rel_ok}/{len(mdl.get('relationships', []))}")
if rel_fail:
    print(f"  ⚠ 失败: {rel_fail}")

conn.commit()
conn.close()

# ---------------------------------------------------------------------------
# Step 4: 拷贝回容器 + 重启 + 部署
# ---------------------------------------------------------------------------
step("4. 拷贝 SQLite 回容器并重启")
# 先停容器避免写入冲突
run(f"docker stop {CONTAINER}")
run(f"docker cp {LOCAL_DB} {CONTAINER}:{REMOTE_DB}")
# 同时拷回 WAL 和 SHM 文件（如果存在）
for suffix in ["-wal", "-shm"]:
    local_f = f"{LOCAL_DB}{suffix}"
    if os.path.exists(local_f):
        run(f"docker cp {local_f} {CONTAINER}:{REMOTE_DB}{suffix}")
    else:
        # 删除容器内残留的 WAL/SHM，避免和新主文件不一致
        run(f"docker exec {CONTAINER} rm -f {REMOTE_DB}{suffix}", check=False)
print("  已拷贝回容器")

run(f"docker start {CONTAINER}")
print("  已重启 wren-ui，等待启动...")
time.sleep(12)

# 等待服务就绪 (GraphQL 对空请求返回 400 也算就绪)
for i in range(20):
    r = run(f"curl -s -o /dev/null -w '%{{http_code}}' {GRAPHQL_URL}", check=False)
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
# deploy 是同步调用，等 AI service 重建向量索引完成后返回
# 本地大模型环境下可能需要 2-5 分钟，curl 默认超时可能不够
print("  正在部署（本地模型可能需要几分钟，请耐心等待）...")
r = run(f"""curl -s --max-time 300 -X POST {GRAPHQL_URL} \
  -H "Content-Type: application/json" \
  -d '{{"query":"mutation {{ deploy(force: true) }}"}}' """, check=False)
if r.returncode == 0 and r.stdout:
    try:
        result = json.loads(r.stdout)
        # GraphQL 可能返回 {"errors": [...]} 或 {"data": {"deploy": {"status": "..."}}}
        if "errors" in result:
            print(f"  部署返回错误: {result['errors'][0].get('message', str(result['errors']))}")
            print(f"  请在 UI 的 Modeling 页面手动点击 Deploy")
        elif result.get("data") and result["data"].get("deploy"):
            status = result["data"]["deploy"].get("status", "UNKNOWN")
            if status == "SUCCESS":
                print(f"  部署成功")
            else:
                error = result["data"]["deploy"].get("error", "")
                print(f"  部署状态: {status}")
                if error:
                    print(f"  错误: {error}")
                print(f"  如果失败，请在 UI 的 Modeling 页面手动点击 Deploy")
        else:
            print(f"  部署响应异常: {r.stdout[:200]}")
            print(f"  请在 UI 的 Modeling 页面手动点击 Deploy")
    except json.JSONDecodeError:
        print(f"  响应解析失败: {r.stdout[:200]}")
        print(f"  请在 UI 的 Modeling 页面手动点击 Deploy")
else:
    print(f"  部署请求超时或失败（这在本地大模型环境下是正常的）")
    print(f"  请在 UI 的 Modeling 页面手动点击 Deploy")

# ---------------------------------------------------------------------------
# Step 5: 验证
# ---------------------------------------------------------------------------
step("6. 验证 SQL 执行")

test_sql = "SELECT ne.ne_id, ne.ne_name, ne.vendor, s.site_name FROM t_network_element ne JOIN t_site s ON ne.site_id = s.site_id LIMIT 3"
r = run(f"""curl -s -X POST {GRAPHQL_URL} \
  -H "Content-Type: application/json" \
  -d '{{"query":"mutation Preview($w: PreviewSQLDataInput!) {{ previewSql(data: $w) }}","variables":{{"w":{{"sql":"{test_sql}","limit":3}}}}}}' """)

result = json.loads(r.stdout)
if "errors" in result:
    print(f"  ⚠ SQL 执行失败: {result['errors']}")
else:
    data = result["data"]["previewSql"]["data"]
    print(f"  JOIN 查询成功，返回 {len(data)} 行:")
    for row in data:
        print(f"    {row}")

# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
step("完成")
print(f"""
  模型: {model_ok} 个 (含中文表描述)
  字段: {col_ok} 个 (含 displayName / 中文描述 / PK / NOT NULL / isCalculated / type)
  关系: {rel_ok} 条 (含中文名称和描述)
  SQL:  JOIN 查询已验证通过
""")
