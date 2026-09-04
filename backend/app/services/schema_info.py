"""資料庫檢視頁（admin 專用，SPEC.md §6.7）。

表名無法用 asyncpg 參數化，白名單（`BUSINESS_TABLES`）是唯一擋 SQL injection
的防線——白名單外一律 400，不是直接拼進 SQL。
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import asyncpg

from app.config.tables import BUSINESS_TABLES
from app.utils.errors import AppError

PREVIEW_ROW_LIMIT = 20
_TAIPEI = ZoneInfo("Asia/Taipei")


def _to_display_value(value):
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(_TAIPEI).isoformat()
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    return value


async def _primary_key_columns(pool: asyncpg.Pool, table: str) -> list[str]:
    rows = await pool.fetch(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public' AND tc.table_name = $1
        ORDER BY kcu.ordinal_position
        """,
        table,
    )
    return [row["column_name"] for row in rows]


async def get_schema_overview(pool: asyncpg.Pool) -> dict:
    columns_rows = await pool.fetch(
        """
        SELECT table_name, column_name, data_type, is_nullable, column_default, ordinal_position
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ANY($1::text[])
        ORDER BY table_name, ordinal_position
        """,
        BUSINESS_TABLES,
    )
    pk_rows = await pool.fetch(
        """
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'
          AND tc.table_name = ANY($1::text[])
        """,
        BUSINESS_TABLES,
    )
    fk_rows = await pool.fetch(
        """
        SELECT tc.table_name, kcu.column_name,
               ccu.table_name AS foreign_table_name, ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
          AND tc.table_name = ANY($1::text[])
        """,
        BUSINESS_TABLES,
    )

    pk_lookup = {(row["table_name"], row["column_name"]) for row in pk_rows}
    fk_lookup = {
        (row["table_name"], row["column_name"]): {
            "table": row["foreign_table_name"],
            "column": row["foreign_column_name"],
        }
        for row in fk_rows
    }

    tables: dict[str, list[dict]] = {table: [] for table in BUSINESS_TABLES}
    for row in columns_rows:
        key = (row["table_name"], row["column_name"])
        tables[row["table_name"]].append(
            {
                "name": row["column_name"],
                "type": row["data_type"],
                "nullable": row["is_nullable"] == "YES",
                "default": row["column_default"],
                "is_primary_key": key in pk_lookup,
                "is_foreign_key": key in fk_lookup,
                "references": fk_lookup.get(key),
            }
        )

    return {"tables": tables}


async def get_table_preview(pool: asyncpg.Pool, table: str) -> list[dict]:
    if table not in BUSINESS_TABLES:
        raise AppError(400, "不支援檢視此資料表。", "VALIDATION_ERROR")

    pk_columns = await _primary_key_columns(pool, table)
    order_clause = f"ORDER BY {', '.join(pk_columns)}" if pk_columns else ""
    rows = await pool.fetch(f"SELECT * FROM {table} {order_clause} LIMIT {PREVIEW_ROW_LIMIT}")

    result = []
    for row in rows:
        record = dict(row)
        if table == "users" and "password_hash" in record:
            record["password_hash"] = "******"
        result.append({key: _to_display_value(value) for key, value in record.items()})
    return result
