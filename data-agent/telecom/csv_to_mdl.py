"""
Convert the NMS field dictionary CSV into WrenAI MDL JSON format.

Usage:
    python -m telecom.csv_to_mdl
"""

import csv
import json
import re
from collections import OrderedDict
from pathlib import Path

# ---------------------------------------------------------------------------
# Table-level Chinese descriptions
# ---------------------------------------------------------------------------
TABLE_DESCRIPTIONS: dict[str, str] = {
    "t_site": "站点/机房表 - 物理机房、POP点的地理位置和基础设施信息",
    "t_network_element": "网元/设备表 - 路由器、交换机等网络设备信息",
    "t_board": "单板表 - 设备内的线卡、主控板等板卡信息",
    "t_interface": "接口表 - 物理口、逻辑口、Trunk等接口信息",
    "t_physical_link": "物理链路表 - 两接口间的光纤/电缆连接",
    "t_vrf_instance": "VRF实例表 - PE设备上的VPN路由转发实例",
    "t_l3vpn_service": "L3VPN业务表 - 端到端VPN服务实例",
    "t_vpn_pe_binding": "VPN-PE绑定表 - VPN与PE设备的多对多关联",
    "t_srv6_policy": "SRv6 Policy表 - SRv6 TE隧道策略",
    "t_tunnel": "隧道表 - SRv6/MPLS逻辑隧道",
    "t_ne_perf_kpi": "网元性能KPI表 - CPU/内存/温度等设备级指标",
    "t_interface_perf_kpi": "接口性能KPI表 - 流量/带宽利用率/错包等接口级指标",
    "t_tunnel_perf_kpi": "隧道性能KPI表 - 时延/抖动/丢包等隧道级指标",
    "t_vpn_sla_kpi": "VPN SLA KPI表 - 端到端SLA达标情况",
}

# Columns whose example_values should be appended to the description when
# they look like enumeration values.
_ENUM_COLUMN_NAMES = {
    "site_type", "ne_type", "vendor", "role", "service_level",
    "board_type", "if_type", "phy_type", "link_type", "tunnel_type",
    "vpn_type", "topology", "underlay_type", "provision_type",
    "sla_type", "address_family", "label_mode", "evpn_type",
    "service_type", "pe_role", "routing_protocol", "encapsulation",
    "protection_type", "group_type", "signaling_protocol",
    "deploy_source", "deploy_status", "qos_class_applied",
    "cooling_type", "tier", "port_type", "sla_class",
    "admin_status", "oper_status", "status",
}


# ---------------------------------------------------------------------------
# Type normalisation helpers
# ---------------------------------------------------------------------------
_TYPE_MAP: dict[str, str] = {
    "BIGSERIAL": "BIGINT",
    "SERIAL": "INT",
    "TEXT": "TEXT",
    "BOOLEAN": "BOOLEAN",
    "BOOL": "BOOLEAN",
    "DATE": "DATE",
    "TIMESTAMP": "TIMESTAMP",
}


def normalise_type(raw: str) -> str:
    """Strip length/precision specifiers and map aliases to MDL basic types."""
    upper = raw.strip().upper()

    # Direct alias lookup first
    if upper in _TYPE_MAP:
        return _TYPE_MAP[upper]

    # Strip parenthesised length / precision: VARCHAR(64) -> VARCHAR
    base = re.sub(r"\(.*\)", "", upper).strip()

    # Replace period-based precision notation: DECIMAL10.2 (after paren strip)
    # Handle raw forms like DECIMAL(10.2) which become DECIMAL after strip
    base = re.sub(r"\d+\.?\d*$", "", base).strip()

    if base in _TYPE_MAP:
        return _TYPE_MAP[base]

    # Map common bases
    if base.startswith("VARCHAR") or base.startswith("CHAR"):
        return "VARCHAR"
    if base in ("INT", "INTEGER", "SMALLINT", "TINYINT"):
        return "INT"
    if base in ("BIGINT",):
        return "BIGINT"
    if base.startswith("DECIMAL") or base.startswith("NUMERIC") or base.startswith("FLOAT") or base.startswith("DOUBLE"):
        return "DECIMAL"
    if base == "TIMESTAMP":
        return "TIMESTAMP"

    # Fallback: return the cleaned base
    return base if base else "VARCHAR"


# ---------------------------------------------------------------------------
# Column description enrichment
# ---------------------------------------------------------------------------
def _should_append_enum(column_name: str, domain: str, example_values: str) -> bool:
    """Decide whether example values represent an enumeration worth appending."""
    if "枚举" in domain:
        return True
    if column_name in _ENUM_COLUMN_NAMES:
        return True
    return False


def build_column_description(chinese_desc: str, column_name: str,
                             domain: str, example_values: str) -> str:
    """Build a rich column description, appending enum values when relevant."""
    desc = chinese_desc
    if _should_append_enum(column_name, domain, example_values):
        clean = example_values.strip().strip('"')
        if clean and clean != "-":
            desc = f"{desc}。取值: {clean}"
    return desc


# ---------------------------------------------------------------------------
# Core MDL generation
# ---------------------------------------------------------------------------
def generate_mdl(csv_path: str | Path) -> dict:
    """Read *csv_path* and return a complete WrenAI MDL dict."""

    csv_path = Path(csv_path)

    # ---- 1. Parse CSV and group rows by table ----
    tables: OrderedDict[str, list[dict]] = OrderedDict()
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            table = row["table"].strip()
            tables.setdefault(table, []).append(row)

    models: list[dict] = []
    relationships: list[dict] = []

    for table_name, rows in tables.items():
        columns: list[dict] = []
        primary_key: str | None = None

        for row in rows:
            col_name = row["column"].strip()
            domain = row.get("domain", "").strip()
            nullable = row.get("nullable", "YES").strip().upper()
            english_term = row.get("english_term", col_name).strip()
            chinese_desc = row.get("chinese_desc", "").strip()
            example_values = row.get("example_values", "").strip()
            raw_type = row.get("data_type", "VARCHAR").strip()
            fk_raw = row.get("foreign_key", "-").strip()

            # Primary key detection
            if domain == "PK":
                primary_key = col_name

            # Build column entry
            col_entry = {
                "name": col_name,
                "type": normalise_type(raw_type),
                "isCalculated": False,
                "notNull": nullable == "NO",
                "expression": col_name,
                "properties": {
                    "displayName": english_term,
                    "description": build_column_description(
                        chinese_desc, col_name, domain, example_values
                    ),
                },
            }
            columns.append(col_entry)

            # Relationship from foreign key
            if fk_raw not in ("-", "") and "引用同表" not in fk_raw:
                # Expected format: target_table.target_column
                if "." in fk_raw:
                    target_table, target_col = fk_raw.split(".", 1)
                    rel_name = f"{table_name}_{col_name}_{target_table}_{target_col}"
                    relationships.append({
                        "name": rel_name,
                        "models": [table_name, target_table],
                        "joinType": "MANY_TO_ONE",
                        "condition": f"{table_name}.{col_name} = {target_table}.{target_col}",
                    })

        # Build model
        model: dict = {
            "name": table_name,
            "tableReference": {"table": table_name},
            "columns": columns,
            "primaryKey": primary_key or "",
            "properties": {
                "displayName": table_name,
                "description": TABLE_DESCRIPTIONS.get(table_name, table_name),
            },
        }
        models.append(model)

    mdl = {
        "catalog": "telecom_nms",
        "schema": "public",
        "dataSource": "DUCKDB",
        "models": models,
        "relationships": relationships,
        "metrics": [],
        "views": [],
        "enumDefinitions": [],
        "macros": [],
    }
    return mdl


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------
def main() -> None:
    csv_path = Path(__file__).resolve().parent.parent / "WrenAI" / "nms_field_dictionary_full.csv"
    output_path = Path(__file__).resolve().parent.parent / "telecom_mdl.json"

    mdl = generate_mdl(csv_path)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(mdl, f, ensure_ascii=False, indent=2)

    print(f"MDL written to {output_path}")
    print(f"  Models: {len(mdl['models'])}")
    print(f"  Relationships: {len(mdl['relationships'])}")
    total_cols = sum(len(m["columns"]) for m in mdl["models"])
    print(f"  Total columns: {total_cols}")


if __name__ == "__main__":
    main()
