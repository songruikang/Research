#!/usr/bin/env python3
"""
Step 1: 从 MDL 生成 DuckDB 数据库（DDL + mock 数据）

输入: telecom/input/telecom_mdl.json
输出: telecom/output/telecom_nms.duckdb

用法:
    python telecom/scripts/1_generate_data.py
"""

import json
import os
import sys
from pathlib import Path

TELECOM_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = TELECOM_DIR / "input"
OUTPUT_DIR = TELECOM_DIR / "output"
MDL_PATH = INPUT_DIR / "telecom_mdl.json"
DB_PATH = OUTPUT_DIR / "telecom_nms.duckdb"

# 表的拓扑排序（外键依赖顺序）
TABLE_ORDER = [
    "t_site",
    "t_network_element",
    "t_board",
    "t_interface",
    "t_physical_link",
    "t_vrf_instance",
    "t_l3vpn_service",
    "t_vpn_pe_binding",
    "t_srv6_policy",
    "t_tunnel",
    "t_ne_perf_kpi",
    "t_interface_perf_kpi",
    "t_tunnel_perf_kpi",
    "t_vpn_sla_kpi",
]


def mdl_to_ddl(mdl: dict) -> list[str]:
    """从 MDL JSON 生成 CREATE TABLE DDL 语句列表（按外键拓扑排序）"""
    models_by_name = {m["name"]: m for m in mdl["models"]}
    relationships = mdl.get("relationships", [])

    # 构建外键映射: {from_table: [(from_col, to_table, to_col), ...]}
    fk_map = {}
    for rel in relationships:
        models = rel["models"]
        if len(models) != 2:
            continue
        condition = rel["condition"]  # e.g. "t_board.ne_id = t_network_element.ne_id"
        parts = condition.split("=")
        left = parts[0].strip().split(".")
        right = parts[1].strip().split(".")
        from_table, from_col = left[0], left[1]
        to_table, to_col = right[0], right[1]
        fk_map.setdefault(from_table, []).append((from_col, to_table, to_col))

    ddl_statements = []
    for table_name in TABLE_ORDER:
        model = models_by_name.get(table_name)
        if not model:
            continue

        pk = model.get("primaryKey", "")
        columns_sql = []

        for col in model.get("columns", []):
            if col.get("isHidden"):
                continue
            name = col["name"]
            col_type = col["type"]
            parts = [name, col_type]
            if col.get("notNull"):
                parts.append("NOT NULL")
            columns_sql.append("  " + " ".join(parts))

        # Primary key
        if pk:
            columns_sql.append(f"  PRIMARY KEY({pk})")

        # Foreign keys
        for from_col, to_table, to_col in fk_map.get(table_name, []):
            columns_sql.append(
                f"  FOREIGN KEY ({from_col}) REFERENCES {to_table}({to_col})"
            )

        ddl = f"CREATE TABLE {table_name} (\n" + ",\n".join(columns_sql) + "\n)"
        ddl_statements.append(ddl)

    return ddl_statements


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 删除旧数据库
    if DB_PATH.exists():
        DB_PATH.unlink()

    print(f"输入: {MDL_PATH}")
    print(f"输出: {DB_PATH}")
    print()

    # 加载 MDL
    with open(MDL_PATH) as f:
        mdl = json.load(f)
    print(f"MDL: {len(mdl['models'])} 个模型, {len(mdl.get('relationships', []))} 条关系")

    # 生成 DDL
    ddl_statements = mdl_to_ddl(mdl)
    print(f"DDL: {len(ddl_statements)} 条建表语句")

    # 连接 DuckDB，建表
    try:
        import duckdb
    except ImportError:
        print("需要安装 duckdb: uv pip install duckdb")
        sys.exit(1)

    conn = duckdb.connect(str(DB_PATH))
    for ddl in ddl_statements:
        conn.execute(ddl)
    print(f"建表完成")
    print()

    # 生成 mock 数据
    # 将 _internal 加入 path
    sys.path.insert(0, str(TELECOM_DIR))
    from _internal.generate_mock_data import populate_data

    populate_data(conn)
    conn.close()

    print(f"\n数据库已写入: {DB_PATH}")


if __name__ == "__main__":
    main()
