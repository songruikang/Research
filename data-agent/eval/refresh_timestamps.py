"""
时间戳刷新脚本 — 将 mock 数据的时间对齐到"现在"

策略：
  1. 计算 KPI 表最大 collect_time 与 NOW() 的差值 (time_delta)
  2. 所有 TIMESTAMP 字段加上 time_delta（整体平移）
  3. 所有 DATE 字段按同样的天数平移
  4. 保持数据内部的时间关系不变

用法：
  python refresh_timestamps.py                  # 刷新 telecom_nms.duckdb
  python refresh_timestamps.py --dry-run        # 只显示要执行的 SQL，不执行
  python refresh_timestamps.py --db other.duckdb
"""

import duckdb
import argparse
import sys
from pathlib import Path


# ── 需要刷新的表和字段 ──

TIMESTAMP_COLUMNS = [
    # KPI 表（核心：这些表的 collect_time 决定时间窗口查询是否有数据）
    ("t_ne_perf_kpi",        ["collect_time", "created_at"]),
    ("t_interface_perf_kpi", ["collect_time", "created_at"]),
    ("t_tunnel_perf_kpi",    ["collect_time", "created_at"]),
    ("t_vpn_sla_kpi",        ["collect_time", "created_at"]),

    # 设备/拓扑表的时间戳
    ("t_network_element",    ["created_at", "updated_at"]),
    ("t_board",              ["last_reboot_time", "created_at", "updated_at"]),
    ("t_interface",          ["last_change_time", "created_at", "updated_at"]),
    ("t_physical_link",      ["created_at", "updated_at"]),
    ("t_vrf_instance",       ["created_at", "updated_at"]),
    ("t_l3vpn_service",      ["last_audit_time", "created_at", "updated_at"]),
    ("t_vpn_pe_binding",     ["created_at", "updated_at"]),
    ("t_srv6_policy",        ["last_path_change", "created_at", "updated_at"]),
    ("t_tunnel",             ["created_at", "updated_at"]),
]

DATE_COLUMNS = [
    # 日期字段平移（合同、上线日期等）
    ("t_site",               ["commissioning_date", "contract_expire_date"]),
    ("t_network_element",    ["commissioning_date", "maintenance_expire"]),
    ("t_board",              ["install_date"]),
    ("t_physical_link",      ["commissioning_date", "contract_expire_date"]),
    ("t_l3vpn_service",      ["contract_start_date", "contract_end_date"]),
]


def get_time_delta(conn):
    """计算 KPI 最大时间与当前时间的差值"""
    result = conn.execute("""
        SELECT MAX(collect_time) AS max_kpi_time,
               CURRENT_TIMESTAMP AS now_time
        FROM t_ne_perf_kpi
    """).fetchone()

    max_kpi = result[0]
    now = result[1]

    print(f"KPI 最大时间:  {max_kpi}")
    print(f"当前时间:      {now}")

    # 用 DuckDB 计算精确的 interval（秒）
    delta_seconds = conn.execute(f"""
        SELECT EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - TIMESTAMP '{max_kpi}'))::BIGINT
    """).fetchone()[0]

    delta_days = delta_seconds // 86400

    # 向下取整到小时（避免分钟级别的碎片）
    delta_hours = delta_seconds // 3600

    print(f"时间差:        {delta_days} 天 ({delta_hours} 小时)")
    print(f"平移策略:      所有时间字段 + INTERVAL {delta_hours} HOUR")

    return delta_hours, delta_days


def build_sql_statements(delta_hours, delta_days):
    """生成所有 UPDATE SQL"""
    statements = []

    for table, columns in TIMESTAMP_COLUMNS:
        set_clauses = []
        for col in columns:
            set_clauses.append(
                f"{col} = {col} + INTERVAL {delta_hours} HOUR"
            )
        sql = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {columns[0]} IS NOT NULL;"
        statements.append((table, sql))

    for table, columns in DATE_COLUMNS:
        set_clauses = []
        for col in columns:
            set_clauses.append(
                f"{col} = {col} + INTERVAL {delta_days} DAY"
            )
        where = " OR ".join(f"{col} IS NOT NULL" for col in columns)
        sql = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {where};"
        statements.append((table, sql))

    return statements


def refresh(db_path, dry_run=False):
    """执行刷新"""
    conn = duckdb.connect(db_path, read_only=dry_run)

    print("=" * 60)
    print("  时间戳刷新")
    print("=" * 60)
    print()

    delta_hours, delta_days = get_time_delta(conn)
    print()

    if delta_hours < 24:
        print("时间差小于 24 小时，无需刷新。")
        conn.close()
        return

    statements = build_sql_statements(delta_hours, delta_days)

    for table, sql in statements:
        if dry_run:
            print(f"[DRY RUN] {sql}")
        else:
            try:
                conn.execute(sql)
                print(f"  ✅ {table}: {sql[:70]}...")
            except Exception as e:
                print(f"  ❌ {table}: {str(e)[:80]}")

    if not dry_run:
        # 验证刷新结果
        print()
        print("刷新后验证:")
        for table in ["t_ne_perf_kpi", "t_interface_perf_kpi", "t_tunnel_perf_kpi", "t_vpn_sla_kpi"]:
            r = conn.execute(f"SELECT MIN(collect_time)::VARCHAR, MAX(collect_time)::VARCHAR FROM {table}").fetchone()
            print(f"  {table}: {r[0]} ~ {r[1]}")

        # 验证时间窗口查询有数据
        print()
        print("时间窗口查询验证:")
        checks = [
            ("过去24小时 NE KPI", "SELECT COUNT(*) FROM t_ne_perf_kpi WHERE collect_time >= CURRENT_TIMESTAMP - INTERVAL 24 HOUR"),
            ("过去7天 NE KPI", "SELECT COUNT(*) FROM t_ne_perf_kpi WHERE collect_time >= CURRENT_TIMESTAMP - INTERVAL 7 DAY"),
            ("过去30天 VPN SLA", "SELECT COUNT(*) FROM t_vpn_sla_kpi WHERE collect_time >= CURRENT_TIMESTAMP - INTERVAL 30 DAY"),
            ("过去7天 IF KPI", "SELECT COUNT(*) FROM t_interface_perf_kpi WHERE collect_time >= CURRENT_TIMESTAMP - INTERVAL 7 DAY"),
            ("过去7天 Tunnel KPI", "SELECT COUNT(*) FROM t_tunnel_perf_kpi WHERE collect_time >= CURRENT_TIMESTAMP - INTERVAL 7 DAY"),
        ]
        for name, sql in checks:
            count = conn.execute(sql).fetchone()[0]
            status = "✅" if count > 0 else "❌"
            print(f"  {status} {name}: {count} 行")

    conn.close()
    print()
    print("完成。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="刷新 mock 数据时间戳")
    default_db = str(Path(__file__).resolve().parent.parent / "telecom_nms.duckdb")
    parser.add_argument("--db", default=default_db, help="DuckDB 文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只显示 SQL 不执行")
    args = parser.parse_args()

    refresh(args.db, dry_run=args.dry_run)
