import argparse
import sys

from db_schema import TABLES
from db_utils import get_db_conn
from dotenv import load_dotenv
from loguru import logger

load_dotenv()


def initialize_database() -> None:
    logger.info("Initializing MotherDuck / DuckDB tables...")
    conn = get_db_conn()

    for table in TABLES:
        col_defs_list = [f"{col} {ctype}" for col, ctype in table.column_types.items()]

        if table.primary_key:
            pk_str = ", ".join(table.primary_key)
            col_defs_list.append(f"PRIMARY KEY ({pk_str})")

        col_defs = ", ".join(col_defs_list)
        create_stmt = f"CREATE TABLE IF NOT EXISTS {table.name} ({col_defs})"

        try:
            conn.execute(create_stmt)
            logger.info(f"Successfully verified/created table: {table.name}")

            # Lightweight schema migration for missing columns
            for col, ctype in table.column_types.items():
                alter_stmt = f"ALTER TABLE {table.name} ADD COLUMN IF NOT EXISTS {col} {ctype.strip()}"
                try:
                    conn.execute(alter_stmt)
                except Exception as alter_err:
                    logger.debug(f"Col {col} check on {table.name}: {alter_err}")

            # Create secondary indexes if defined
            for idx_cols in table.indexes:
                idx_name = f"idx_{table.name}_{'_'.join(idx_cols)}"
                cols_str = ", ".join(idx_cols)
                try:
                    conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table.name}({cols_str})")
                except Exception as idx_err:
                    logger.debug(f"Index creation notice on {table.name}: {idx_err}")

            # Apply table description comment to MotherDuck catalog
            if table.description:
                try:
                    desc_escaped = table.description.replace("'", "''")
                    conn.execute(f"COMMENT ON TABLE {table.name} IS '{desc_escaped}'")
                except Exception as tbl_cm_err:
                    logger.debug(f"Table comment failed on {table.name}: {tbl_cm_err}")

            # Apply column description comments to MotherDuck catalog
            for col, comment in table.column_descriptions.items():
                try:
                    comment_escaped = comment.replace("'", "''")
                    conn.execute(f"COMMENT ON COLUMN {table.name}.{col} IS '{comment_escaped}'")
                except Exception as col_cm_err:
                    logger.debug(f"Column comment failed on {table.name}.{col}: {col_cm_err}")

        except Exception as e:
            logger.error(f"Failed to initialize table {table.name}: {e}")
            raise

    conn.close()
    logger.success("Database initialization complete.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize MotherDuck DB Schemas")
    parser.parse_args()

    try:
        initialize_database()
        return 0
    except Exception as e:
        logger.exception(f"Initialization failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
