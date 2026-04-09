#!/usr/bin/env python3
"""
从 DuckDB 导出 Init SQL（CREATE TABLE + INSERT INTO），用于 WrenAI 导入。

使用方式：
    python telecom/scripts/export_init_sql.py --output telecom_init.sql

然后在 WrenAI UI 的 "Init SQL" 框中粘贴 telecom_init.sql 的内容。

前提：
    - telecom_nms.duckdb 需要先用 generate_mock_data.py 生成
    - 导出约 21000 行 SQL（14 张表的 DDL + 数据）
"""

import argparse
import sys
from pathlib import Path

try:
    import duckdb
except ImportError:
    print("需要安装 duckdb: pip install duckdb")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = PROJECT_ROOT / "telecom_nms.duckdb"

# 表的拓扑排序（外键依赖顺序，被引用的表在前）
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


def export_init_sql(db_path: str) -> str:
    """从 DuckDB 导出完整的 Init SQL"""
    conn = duckdb.connect(db_path, read_only=True)
    parts = []

    for table in TABLE_ORDER:
        # DDL
        ddl = conn.execute(
            f"SELECT sql FROM duckdb_tables() WHERE table_name = '{table}'"
        ).fetchone()
        if not ddl:
            print(f"  跳过 {table}（不存在）")
            continue
        parts.append(f"-- === {table} ===")
        parts.append(ddl[0] + ";")
        parts.append("")

        # INSERT 数据
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        cols = [desc[0] for desc in conn.execute(f"SELECT * FROM {table} LIMIT 0").description]
        col_names = ", ".join(cols)

        for row in rows:
            values = []
            for v in row:
                if v is None:
                    values.append("NULL")
                elif isinstance(v, bool):
                    values.append("TRUE" if v else "FALSE")
                elif isinstance(v, (int, float)):
                    values.append(str(v))
                else:
                    # 转义单引号
                    escaped = str(v).replace("'", "''")
                    values.append(f"'{escaped}'")
            parts.append(f"INSERT INTO {table} ({col_names}) VALUES ({', '.join(values)});")

        parts.append("")
        print(f"  {table}: {len(rows)} rows")

    conn.close()
    return "\n".join(parts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从 DuckDB 导出 WrenAI Init SQL")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="DuckDB 文件路径")
    parser.add_argument("--output", "-o", default="telecom_init.sql",
                        help="输出 SQL 文件路径（默认 telecom_init.sql）")
    args = parser.parse_args()

    print("导出 Init SQL ...")
    sql = export_init_sql(args.db)
    line_count = sql.count("\n") + 1
    print(f"  共 {line_count} 行")

    with open(args.output, "w") as f:
        f.write(sql)
    print(f"\n已保存到 {args.output}")
    print(f"下一步: 在 WrenAI UI 的 Init SQL 框中粘贴此文件内容")
