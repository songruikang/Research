#!/usr/bin/env python3
"""
导出 WrenAI 所需的 Init SQL + CSV 数据文件。

使用方式：
    python telecom/scripts/export_init_sql.py

产出：
    1. WrenAI/docker/data/csv/*.csv    — 14 张表的数据文件（挂载到容器内）
    2. telecom_init.sql                — 56 行 Init SQL（粘贴到 WrenAI UI）

Init SQL 只有 DDL + read_csv_auto() 语句，不含实际数据，
数据通过 Docker volume 挂载的 CSV 文件加载。

前提：
    - telecom_nms.duckdb 需要先用 generate_mock_data.py 生成
"""

import argparse
import os
import sys
from pathlib import Path

try:
    import duckdb
except ImportError:
    print("需要安装 duckdb: pip install duckdb")
    sys.exit(1)

TELECOM_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = TELECOM_DIR.parent
OUTPUT_DIR = TELECOM_DIR / "output"
DEFAULT_DB = OUTPUT_DIR / "telecom_nms.duckdb"
# CSV 文件存放在 WrenAI/docker/data/，通过 docker-compose volume 挂载到容器
DEFAULT_CSV_DIR = PROJECT_ROOT / "WrenAI" / "docker" / "data"

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

# CSV 文件在 Docker 容器内的路径
# docker-compose.yaml 中 wren-engine 挂载: ${PROJECT_DIR}/data:/usr/src/app/data
CSV_CONTAINER_DIR = "/usr/src/app/data"


def export_csv(conn, csv_dir: Path):
    """导出每张表为 CSV 文件"""
    csv_dir.mkdir(parents=True, exist_ok=True)
    for table in TABLE_ORDER:
        path = csv_dir / f"{table}.csv"
        conn.execute(f"COPY {table} TO '{path}' (HEADER, DELIMITER ',')")
        rows = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {rows} rows -> {path.name}")


def export_init_sql(conn) -> str:
    """生成 Init SQL（DDL + read_csv_auto）"""
    parts = []
    for table in TABLE_ORDER:
        ddl_row = conn.execute(
            f"SELECT sql FROM duckdb_tables() WHERE table_name = '{table}'"
        ).fetchone()
        if not ddl_row:
            continue
        ddl = ddl_row[0].rstrip(";")
        rows = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        parts.append(f"-- {table} ({rows} rows)")
        parts.append(f"{ddl};")
        parts.append(
            f"INSERT INTO {table} SELECT * FROM read_csv_auto("
            f"'{CSV_CONTAINER_DIR}/{table}.csv', header=true);"
        )
        parts.append("")
    return "\n".join(parts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导出 WrenAI Init SQL + CSV")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="DuckDB 文件路径")
    parser.add_argument("--csv-dir", default=str(DEFAULT_CSV_DIR),
                        help="CSV 输出目录（默认 WrenAI/docker/data/csv/）")
    parser.add_argument("--output", "-o", default=str(OUTPUT_DIR / "telecom_init.sql"),
                        help="Init SQL 输出路径")
    args = parser.parse_args()

    conn = duckdb.connect(args.db, read_only=True)

    print("1. 导出 CSV 文件 ...")
    export_csv(conn, Path(args.csv_dir))

    print("\n2. 生成 Init SQL ...")
    sql = export_init_sql(conn)
    conn.close()

    with open(args.output, "w") as f:
        f.write(sql)

    line_count = sql.count("\n") + 1
    print(f"   {line_count} 行 -> {args.output}")
    print(f"""
完成。下一步：
  1. 确认 CSV 文件在 {args.csv_dir}
  2. 启动 WrenAI: cd WrenAI/docker && docker compose --env-file .env.local up -d
  3. 打开 http://localhost:3000
  4. 选择 DuckDB，Display Name 填 telecom_nms
  5. Init SQL 框粘贴 {args.output} 的内容（{line_count} 行）
  6. Next → 全选 14 张表 → Submit
""")
