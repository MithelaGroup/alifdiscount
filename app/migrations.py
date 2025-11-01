# app/migrations.py
from typing import Iterable
from sqlalchemy.engine import Engine

def _pragma_table_info(conn, table: str) -> set[str]:
    rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").all()
    # row tuple: (cid, name, type, notnull, dflt_value, pk)
    return {r[1] for r in rows}

def _has_table(conn, table: str) -> bool:
    r = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(r)

def _add_column(conn, table: str, col_def_sql: str):
    # col_def_sql example: "mobile_bd VARCHAR(20)"
    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col_def_sql}")

def _ensure_columns(conn, table: str, needed: Iterable[tuple[str, str]]):
    if not _has_table(conn, table):
        return
    existing = _pragma_table_info(conn, table)
    for name, ddl in needed:
        if name not in existing:
            _add_column(conn, table, f"{name} {ddl}")

def run_migrations(engine: Engine) -> None:
    """Idempotent, SQLite-only migrations. Safe to run at every startup."""
    if engine.url.get_backend_name() != "sqlite":
        return

    with engine.begin() as conn:  # transactional
        # Make sure FK enforcement is on
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")

        # ---- users table ----
        _ensure_columns(conn, "users", [
            ("mobile_bd", "VARCHAR(20)"),
            ("is_email_verified", "BOOLEAN DEFAULT 0"),
            ("created_at", "DATETIME"),
        ])
        # unique index for mobile (allows many NULLs, OK for SQLite)
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_mobile_bd ON users(mobile_bd)"
        )

        # ---- coupons table ----
        _ensure_columns(conn, "coupons", [
            ("assigned_request_id", "INTEGER"),
            ("assigned_to_name", "VARCHAR(120)"),
            ("assigned_to_mobile", "VARCHAR(20)"),
            ("assigned_by_user_id", "INTEGER"),
            ("assigned_at", "DATETIME"),
            ("is_active", "BOOLEAN DEFAULT 1"),
        ])
        # Keep one-to-one semantics for assignment
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_coupons_assigned_request_id "
            "ON coupons(assigned_request_id)"
        )

        # ---- coupon_requests table ----
        _ensure_columns(conn, "coupon_requests", [
            ("group_id", "INTEGER"),
            ("discount_percent", "INTEGER"),
            ("status", "VARCHAR(20) DEFAULT 'pending'"),
            ("approved_by_user_id", "INTEGER"),
            ("approved_at", "DATETIME"),
            ("done_at", "DATETIME"),
            ("invoice_number", "VARCHAR(64)"),
        ])

        # ---- contacts table ----
        _ensure_columns(conn, "contacts", [
            ("notes", "TEXT"),
        ])
