import argparse
import os
import sqlite3
import sys

from loguru import logger

from config import PipelineConfig
from db_schema import TABLES


def initialize_database() -> None:
    logger.info(f"Initializing database at {PipelineConfig.DB_PATH}")
    os.makedirs(os.path.dirname(PipelineConfig.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(PipelineConfig.DB_PATH)
    cursor = conn.cursor()

    for table in TABLES:
        col_defs = ", ".join(
            [f"{col} {ctype}" for col, ctype in table.columns.items()]
        )
        create_stmt = f"CREATE TABLE IF NOT EXISTS {table.name} ({col_defs})"

        try:
            cursor.execute(create_stmt)
            logger.info(f"Successfully verified/created table: {table.name}")

            # Check for missing columns on existing tables (lightweight migration)
            cursor.execute(f"PRAGMA table_info({table.name})")
            existing_cols = {row[1] for row in cursor.fetchall()}

            for col_name, col_type in table.columns.items():
                if col_name not in existing_cols:
                    logger.info(f"Adding missing column '{col_name}' to {table.name}")
                    alter_stmt = f"ALTER TABLE {table.name} ADD COLUMN {col_name} {col_type}"
                    cursor.execute(alter_stmt)

            for idx in table.indices:
                cursor.execute(idx)
                logger.info(f"Executed index definition for {table.name}")
        except Exception as e:
            logger.error(f"Failed to initialize table {table.name}: {e}")
            raise


    conn.commit()
    conn.close()
    logger.success("Database initialization complete.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize SQLite DB Schemas")
    parser.parse_args()

    try:
        initialize_database()
        return 0
    except Exception as e:
        logger.exception(f"Initialization failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
