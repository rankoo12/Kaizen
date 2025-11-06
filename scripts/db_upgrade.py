"""
Simple DB upgrade helper for environments without Alembic.

Usage:
  KAIZEN_PG_DSN=postgresql://user:pass@host:5432/db python scripts/db_upgrade.py

It reuses PostgresStorage.ensure_schema() to create required tables and indexes.
"""

import os
import sys


def main() -> int:
    dsn = os.environ.get("KAIZEN_PG_DSN")
    if not dsn:
        print("KAIZEN_PG_DSN not set; nothing to do")
        return 0
    try:
        from engine.core.storage.postgres import PostgresStorage

        # Constructing the storage triggers schema ensure
        PostgresStorage(dsn)
        print("DB schema ensured via PostgresStorage")
        return 0
    except Exception as e:
        print(f"db upgrade failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
