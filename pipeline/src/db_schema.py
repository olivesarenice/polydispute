from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class TableConfig:
    name: str
    columns: Dict[str, str]
    indices: List[str] = field(default_factory=list)

def get_dw_columns() -> Dict[str, str]:
    """Standard tracking columns for the Data Warehouse pattern."""
    return {
        "_created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        "_updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        "_removed_at": "DATETIME"
    }

TABLES = [
    TableConfig(
        name="pipeline_runs",
        columns={
            "run_id": "TEXT PRIMARY KEY",
            "mode": "TEXT", # 'batch' or 'incremental'
            "start_time": "DATETIME",
            "end_time": "DATETIME",
            "status": "TEXT",
            "records_processed": "INTEGER"
        }
    ),
    TableConfig(
        name="raw_pm_markets",
        columns={
            "id": "TEXT PRIMARY KEY",
            "question": "TEXT",
            "condition_id": "TEXT",
            "slug": "TEXT",
            "resolution_source": "TEXT",
            "end_date": "TEXT",
            "start_date": "TEXT",
            "description": "TEXT",
            "outcomes": "TEXT",
            "outcome_prices": "TEXT",
            "volume_num": "REAL",
            "active": "INTEGER",
            "closed": "INTEGER",
            "market_maker_address": "TEXT",
            "resolved_by": "TEXT",
            "uma_resolution_status": "TEXT",
            "uma_bond": "REAL",
            "uma_reward": "REAL",
            "custom_liveness": "REAL",
            "neg_risk": "INTEGER",
            "uma_question_id": "TEXT",
            **get_dw_columns()
        },
        indices=["CREATE INDEX IF NOT EXISTS idx_raw_pm_markets_condition ON raw_pm_markets(condition_id)"]
    ),
    TableConfig(
        name="raw_pm_events",
        columns={
            "id": "TEXT PRIMARY KEY",
            "ticker": "TEXT",
            "slug": "TEXT",
            "title": "TEXT",
            "description": "TEXT",
            "start_date": "TEXT",
            "creation_date": "TEXT",
            "end_date": "TEXT",
            "active": "INTEGER",
            "closed": "INTEGER",
            **get_dw_columns()
        }
    ),
    TableConfig(
        name="raw_dc_threads",
        columns={
            "id": "TEXT PRIMARY KEY",
            "parent_channel_id": "TEXT",
            "content": "TEXT",
            "timestamp": "TEXT",
            "author_id": "TEXT",
            "author_username": "TEXT",
            "embeds": "TEXT",
            "thread_metadata": "TEXT",
            **get_dw_columns()
        },
        indices=["CREATE INDEX IF NOT EXISTS idx_raw_dc_parent_channel ON raw_dc_threads(parent_channel_id)"]
    ),
    TableConfig(
        name="raw_dc_messages",
        columns={
            "id": "TEXT PRIMARY KEY",
            "thread_id": "TEXT",
            "content": "TEXT",
            "timestamp": "TEXT",
            "author_id": "TEXT",
            "author_username": "TEXT",
            "embeds": "TEXT",
            **get_dw_columns()
        },
        indices=["CREATE INDEX IF NOT EXISTS idx_raw_dc_thread ON raw_dc_messages(thread_id)"]
    ),
    TableConfig(
        name="raw_polygon_ancillary",
        columns={
            "question_id": "TEXT PRIMARY KEY",
            "adapter_address": "TEXT",
            "oracle_address": "TEXT",
            "oracle_version": "TEXT",
            "ancillary_data_hex": "TEXT",
            "ancillary_data_decoded": "TEXT",
            **get_dw_columns()
        }
    ),
    TableConfig(
        name="clean_pm_markets",
        columns={
            "condition_id": "TEXT PRIMARY KEY",
            "market_id": "TEXT",
            "uma_question_id": "TEXT",
            "slug": "TEXT",
            "question": "TEXT",
            "active": "INTEGER",
            "closed": "INTEGER",
            "uma_resolution_status": "TEXT",
            "uma_bond": "REAL",
            "uma_reward": "REAL",
            "neg_risk": "INTEGER",
            "custom_liveness": "REAL",
            "yes_price": "REAL",
            "no_price": "REAL",
            **get_dw_columns()
        },
        indices=["CREATE INDEX IF NOT EXISTS idx_clean_pm_slug ON clean_pm_markets(slug)"]
    ),
    TableConfig(
        name="clean_dc_threads",
        columns={
            "thread_id": "TEXT PRIMARY KEY",
            "market_id": "TEXT",
            "author_username": "TEXT",
            "timestamp": "TEXT",
            "content": "TEXT",
            **get_dw_columns()
        },
        indices=["CREATE INDEX IF NOT EXISTS idx_clean_dc_qid ON clean_dc_threads(market_id)"]
    ),
    TableConfig(
        name="clean_dc_messages",
        columns={
            "message_id": "TEXT PRIMARY KEY",
            "thread_id": "TEXT",
            "author_username": "TEXT",
            "vote_type": "TEXT",
            "timestamp": "TEXT",
            **get_dw_columns()
        },
        indices=["CREATE INDEX IF NOT EXISTS idx_clean_dc_msg_thread ON clean_dc_messages(thread_id)"]
    ),
    TableConfig(
        name="clean_polygon_ancillary",
        columns={
            "uma_question_id": "TEXT PRIMARY KEY",
            "oracle_version": "TEXT",
            "ancillary_data_decoded": "TEXT",
            **get_dw_columns()
        }
    )
]
