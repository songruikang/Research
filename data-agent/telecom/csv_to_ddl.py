"""
Parse the NMS field dictionary CSV and generate DuckDB-compatible CREATE TABLE DDL.

Usage:
    python csv_to_ddl.py                          # print DDL to stdout
    python csv_to_ddl.py output.sql               # write DDL to file
"""

import csv
import re
import sys
from collections import OrderedDict
from pathlib import Path

# Topological order respecting FK dependencies
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

DEFAULT_CSV_PATH = Path(__file__).resolve().parent.parent / "WrenAI" / "nms_field_dictionary_full.csv"


def _fix_data_type(raw_type: str) -> str:
    """Apply DuckDB compatibility fixes to a data type string."""
    # BIGSERIAL -> BIGINT (DuckDB has no BIGSERIAL)
    if raw_type.strip().upper() == "BIGSERIAL":
        return "BIGINT"
    # DECIMAL(10.7) -> DECIMAL(10,7)  (period to comma inside DECIMAL)
    fixed = re.sub(r"DECIMAL\((\d+)\.(\d+)\)", r"DECIMAL(\1,\2)", raw_type, flags=re.IGNORECASE)
    return fixed


def _is_numeric(value: str) -> bool:
    """Check if a string represents a numeric literal."""
    try:
        float(value)
        return True
    except ValueError:
        return False


def _format_default(value: str) -> str:
    """Convert a raw default value from the CSV into a SQL DEFAULT clause fragment.

    Rules:
      - "-"                  -> None (no default)
      - "CURRENT_TIMESTAMP"  -> CURRENT_TIMESTAMP
      - "TRUE" / "FALSE"     -> TRUE / FALSE
      - numeric strings      -> bare number
      - anything else        -> single-quoted string
    """
    if value.strip() == "-":
        return ""
    val = value.strip()
    upper = val.upper()
    if upper == "CURRENT_TIMESTAMP":
        return f"DEFAULT {val}"
    if upper in ("TRUE", "FALSE"):
        return f"DEFAULT {upper}"
    if _is_numeric(val):
        return f"DEFAULT {val}"
    # String literal – wrap in single quotes
    return f"DEFAULT '{val}'"


def parse_csv(csv_path: str | None = None) -> dict:
    """Parse the field-dictionary CSV and group rows by table name.

    Returns:
        dict  –  {table_name: [list of column dicts]}
        Each column dict keeps the original CSV keys.
    """
    csv_path = csv_path or str(DEFAULT_CSV_PATH)
    tables: dict[str, list[dict]] = OrderedDict()
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            table = row["table"].strip()
            tables.setdefault(table, []).append(row)
    return tables


def generate_ddl(csv_path: str | None = None) -> list[str]:
    """Generate a list of CREATE TABLE SQL strings in FK-safe order.

    Returns:
        list[str]  –  One CREATE TABLE statement per element.
    """
    tables = parse_csv(csv_path)

    statements: list[str] = []

    for table_name in TABLE_ORDER:
        columns = tables.get(table_name)
        if columns is None:
            continue

        col_defs: list[str] = []
        pk_cols: list[str] = []
        fk_clauses: list[str] = []

        for col in columns:
            col_name = col["column"].strip()
            data_type = _fix_data_type(col["data_type"].strip())
            domain = col["domain"].strip()
            nullable = col["nullable"].strip().upper()
            default_raw = col["default"].strip()
            fk_raw = col["foreign_key"].strip()

            parts = [col_name, data_type]

            # NOT NULL
            if nullable == "NO":
                parts.append("NOT NULL")

            # DEFAULT
            default_clause = _format_default(default_raw)
            if default_clause:
                parts.append(default_clause)

            # Track PK columns
            if domain == "PK":
                pk_cols.append(col_name)

            # Track FK constraints
            if fk_raw != "-" and "." in fk_raw:
                ref_table, ref_col = fk_raw.split(".", 1)
                fk_clauses.append(
                    f"    FOREIGN KEY ({col_name}) REFERENCES {ref_table}({ref_col})"
                )

            col_defs.append("    " + " ".join(parts))

        # Append table-level PRIMARY KEY
        if pk_cols:
            col_defs.append(f"    PRIMARY KEY ({', '.join(pk_cols)})")

        # Append FK constraints
        col_defs.extend(fk_clauses)

        body = ",\n".join(col_defs)
        stmt = f"CREATE TABLE {table_name} (\n{body}\n);"
        statements.append(stmt)

    return statements


def get_table_metadata(csv_path: str | None = None) -> dict:
    """Return rich metadata per table and column.

    Returns:
        dict  –  {
            table_name: {
                column_name: {
                    "english_term": str,
                    "chinese_desc": str,
                    "example_values": str,
                }
            }
        }
    """
    tables = parse_csv(csv_path)
    metadata: dict[str, dict[str, dict]] = {}
    for table_name, columns in tables.items():
        tbl_meta: dict[str, dict] = {}
        for col in columns:
            col_name = col["column"].strip()
            tbl_meta[col_name] = {
                "english_term": col["english_term"].strip(),
                "chinese_desc": col["chinese_desc"].strip(),
                "example_values": col["example_values"].strip(),
            }
        metadata[table_name] = tbl_meta
    return metadata


if __name__ == "__main__":
    ddl_statements = generate_ddl()
    output = "\n\n".join(ddl_statements)

    if len(sys.argv) > 1:
        out_path = sys.argv[1]
        Path(out_path).write_text(output + "\n", encoding="utf-8")
        print(f"DDL written to {out_path}")
    else:
        print(output)
