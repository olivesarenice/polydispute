# cspell:ignore CLOB
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class TableConfig:
    """
    Data Warehouse table configuration schema.
    Combines SQL types, column catalog descriptions, and table-level constraints/indexes.
    Naming Convention: {datazone}_{source}_{tablename}
    Datazones: raw, clean, stg, mart, view
    Sources: pm (polymarket), dc (discord), pg (polygon), ur (umarocks), sys (system)
    """

    name: str
    description: str
    columns: Dict[str, Tuple[str, str]]  # col_name -> (data_type, description)
    primary_key: List[str] = field(default_factory=list)
    indexes: List[List[str]] = field(
        default_factory=list
    )  # Index column groupings: [["col1"], ["col1", "col2"]]
    partition_by: Optional[str] = None  # e.g. "observed_at" or "_created_at"

    @property
    def column_types(self) -> Dict[str, str]:
        return {col: spec[0] for col, spec in self.columns.items()}

    @property
    def column_descriptions(self) -> Dict[str, str]:
        return {col: spec[1] for col, spec in self.columns.items()}


def get_dw_columns() -> Dict[str, Tuple[str, str]]:
    """Standard tracking columns and descriptions for Data Warehouse audit pattern."""
    return {
        "_created_at": (
            "TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP",
            "UTC time for record insert to table",
        ),
        "_updated_at": (
            "TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP",
            "UTC time for record update in table",
        ),
        "_removed_at": (
            "TIMESTAMPTZ",
            "UTC time for record soft-delete timestamp, NULL if record is active",
        ),
        "_source_table": (
            "VARCHAR[]",
            "Source table or upstream API connector names for lineage tracking",
        ),
        "_source_run_id": (
            "VARCHAR",
            "Pipeline execution batch ID - FK matching raw_sys_pipeline_runs.run_id",
        ),
        "_run_created_at": (
            "TIMESTAMPTZ",
            "UTC time when the pipeline run started",
        ),
    }


TABLES = [
    TableConfig(
        name="raw_sys_pipeline_runs",
        description="Audit log of pipeline runs",
        primary_key=["run_id"],
        indexes=[["status"], ["start_time"]],
        columns={
            "run_id": (
                "VARCHAR",
                "Unique UUID assigned to each pipeline execution run",
            ),
            "mode": (
                "VARCHAR",
                "Execution mode (e.g. 'batch_seed', 'cron_incremental', 'ingestion_dag')",
            ),
            "start_time": (
                "TIMESTAMPTZ",
                "UTC time when pipeline run started",
            ),
            "end_time": (
                "TIMESTAMPTZ",
                "UTC time when pipeline run completed",
            ),
            "status": (
                "VARCHAR",
                "Run status outcome ('RUNNING', 'SUCCESS', 'FAILED')",
            ),
        },
    ),
    TableConfig(
        name="raw_pm_markets",
        description="Raw prediction market metadata ingested from Polymarket Gamma API",
        primary_key=["id"],
        indexes=[["condition_id"], ["slug"], ["uma_question_id"]],
        columns={
            "id": (
                "VARCHAR",
                "Unique numeric string market ID assigned by Polymarket",
            ),
            "question": (
                "VARCHAR",
                "The primary question / proposition title of the market",
            ),
            "condition_id": (
                "VARCHAR",
                "Gnosis CTF 32-byte condition ID (0x hex string)",
            ),
            "slug": (
                "VARCHAR",
                "URL slug for the market on polymarket.com",
            ),
            "resolution_source": (
                "VARCHAR",
                "Text reference or URL specifying the oracle resolution source website",
            ),
            "end_date": (
                "TIMESTAMPTZ",
                "ISO8601 scheduled market closing / question expiration date",
            ),
            "start_date": (
                "TIMESTAMPTZ",
                "ISO8601 timestamp when trading officially opened on Polymarket",
            ),
            "description": (
                "VARCHAR",
                "Full market resolution rules and detailed description string",
            ),
            "outcomes": (
                "VARCHAR[]",
                'Array of outcome labels (e.g. ["Yes", "No"])',
            ),
            "outcome_prices": (
                "DOUBLE[]",
                'Array of current outcome prices (e.g. [0.52, 0.48])',
            ),
            "volume_num": (
                "DOUBLE",
                "Total USD trading volume accumulated on this market",
            ),
            "active": (
                "BOOLEAN",
                "Boolean flag indicating if market is active for trading",
            ),
            "closed": (
                "BOOLEAN",
                "Boolean flag indicating if trading is closed",
            ),
            "market_maker_address": (
                "VARCHAR",
                "Ethereum contract address of the CTF Exchange market maker",
            ),
            "resolved_by": (
                "VARCHAR",
                "UMA CTF Adapter smart contract address that resolved the market",
            ),
            "uma_resolution_status": (
                "VARCHAR",
                "UMA Oracle status ('proposed', 'disputed', 'resolved')",
            ),
            "uma_bond": (
                "DOUBLE",
                "UMA proposal/dispute bond amount in USDC",
            ),
            "uma_reward": (
                "DOUBLE",
                "UMA reward offered for resolving the question",
            ),
            "custom_liveness": (
                "INTEGER",
                "Custom liveness window duration in seconds",
            ),
            "neg_risk": (
                "BOOLEAN",
                "Boolean flag indicating if market belongs to a NegRisk market group",
            ),
            "uma_question_id": (
                "VARCHAR",
                "UMA Optimistic Oracle question identifier (0x hex bytes32); FK matching raw_pg_ancillary.question_id",
            ),
            "clob_token_ids": (
                "VARCHAR[]",
                "Array string of CLOB asset token IDs ['YES_token', 'NO_token']",
            ),
            "closed_time": (
                "TIMESTAMPTZ",
                "ISO8601 timestamp when trading on Polymarket was closed",
            ),
            "uma_end_date": (
                "TIMESTAMPTZ",
                "ISO8601 timestamp when UMA Oracle liveness expired / DVM vote completed and market formally resolved",
            ),
            "category": (
                "VARCHAR",
                "High-level market category (e.g. Crypto, Politics, Pop Culture)",
            ),
            "liquidity_num": ("DOUBLE", "Total USD liquidity available in orderbook"),
            "volume_24hr": ("DOUBLE", "24-hour USD trading volume"),
            **get_dw_columns(),
        },
    ),
    TableConfig(
        name="raw_pm_events",
        description="Raw event group metadata ingested from Polymarket Gamma API",
        primary_key=["id"],
        indexes=[["ticker"], ["slug"]],
        columns={
            "id": (
                "VARCHAR",
                "Unique numeric string event group ID assigned by Polymarket",
            ),
            "ticker": ("VARCHAR", "Event short ticker code"),
            "slug": ("VARCHAR", "URL slug for the event on polymarket.com"),
            "title": ("VARCHAR", "Primary event title / proposition heading"),
            "description": (
                "VARCHAR",
                "Full event scope and detailed description string",
            ),
            "start_date": (
                "TIMESTAMPTZ",
                "ISO8601 event creation / activation date",
            ),
            "creation_date": ("TIMESTAMPTZ", "ISO8601 event creation timestamp"),
            "end_date": (
                "TIMESTAMPTZ",
                "ISO8601 scheduled event closing / expiration date",
            ),
            "active": (
                "BOOLEAN",
                "Boolean flag indicating if event is active for trading",
            ),
            "closed": (
                "BOOLEAN",
                "Boolean flag indicating if trading is closed",
            ),
            "category": (
                "VARCHAR",
                "High-level event category (e.g. Crypto, Politics, Pop Culture)",
            ),
            "volume": (
                "DOUBLE",
                "Total combined USD trading volume accumulated across all markets in event",
            ),
            **get_dw_columns(),
        },
    ),
    TableConfig(
        name="raw_dc_threads",
        description="Raw Discord thread starter messages scraped from UMA #disputes channel",
        primary_key=["id"],
        indexes=[["parent_channel_id"], ["author_id"]],
        columns={
            "id": (
                "VARCHAR",
                "Discord thread snowflake ID (and thread root message ID)",
            ),
            "parent_channel_id": (
                "VARCHAR",
                "Parent Discord channel ID (UMA #disputes = 964000735073284127)",
            ),
            "content": (
                "VARCHAR",
                "Initial thread opener message content (from UMA Herald or user)",
            ),
            "timestamp": ("TIMESTAMPTZ", "ISO8601 Discord message creation timestamp"),
            "author_id": ("VARCHAR", "Discord user ID of thread starter"),
            "author_username": (
                "VARCHAR",
                "Discord username / handle of thread starter",
            ),
            "embeds": ("VARCHAR", "JSON string of attached Discord message embeds"),
            "thread_metadata": (
                "VARCHAR",
                "JSON string of Discord thread metadata (name, member count, archive status)",
            ),
            **get_dw_columns(),
        },
    ),
    TableConfig(
        name="raw_dc_messages",
        description="Raw Discord discussion and voting messages inside dispute threads",
        primary_key=["id"],
        indexes=[["thread_id"], ["author_id"]],
        columns={
            "id": ("VARCHAR", "Discord message snowflake ID"),
            "thread_id": (
                "VARCHAR",
                "Parent Discord thread ID; FK matching raw_dc_threads.id",
            ),
            "content": (
                "VARCHAR",
                "Message body text (contains prediction / vote stance: P1, P2, P3, P4)",
            ),
            "timestamp": ("TIMESTAMPTZ", "ISO8601 message timestamp"),
            "author_id": ("VARCHAR", "Discord user ID of message author"),
            "author_username": ("VARCHAR", "Discord username of message author"),
            "embeds": ("VARCHAR", "JSON string of attached message embeds"),
            **get_dw_columns(),
        },
    ),
    TableConfig(
        name="raw_ur_signals",
        description="UMARocks voting committee consensus ingested from UMA Rocks API (`getPoolAnswers`)",
        primary_key=["id"],
        indexes=[["round_id"]],
        columns={
            "id": (
                "VARCHAR",
                "Synthetic or payload ID for UMA Rocks signal",
            ),
            "question": ("VARCHAR", "Dispute question text"),
            "ancillary_data": (
                "VARCHAR",
                "Ancillary data string attached to DVM vote pool",
            ),
            "answer": (
                "VARCHAR",
                "DVM committee consensus stance ('P1', 'P2', 'P3', 'P4')",
            ),
            "round_id": ("BIGINT", "UMA DVM voting round ID"),
            "timestamp": ("BIGINT", "Unix timestamp of DVM voting round"),
            "timestamp_iso": ("TIMESTAMPTZ", "ISO8601 UTC timestamp calculated from timestamp epoch"),
            "reward": ("DOUBLE", "DVM resolution reward token amount"),
            **get_dw_columns(),
        },
    ),
    TableConfig(
        name="raw_pm_price_history",
        description="High-resolution (1-min) midpoint price time-series ingested from Polymarket CLOB API",
        primary_key=["market_id", "observed_at"],
        indexes=[["market_id"], ["yes_clob_token_id"], ["observed_at"]],
        partition_by="observed_at",
        columns={
            "market_id": (
                "VARCHAR",
                "Foreign key matching raw_pm_markets.id",
            ),
            "yes_clob_token_id": (
                "VARCHAR",
                "Polymarket CLOB asset token ID for the YES outcome token",
            ),
            "yes_price": (
                "DOUBLE",
                "Resampled midpoint trading price for YES token (0.0 to 1.0)",
            ),
            "observed_at": ("BIGINT", "Unix timestamp (seconds) of price bar"),
            "observed_at_iso": ("TIMESTAMPTZ", "ISO8601 UTC timestamp calculated from observed_at"),
            **get_dw_columns(),
        },
    ),
    TableConfig(
        name="clean_pm_markets",
        description="Clean prediction market dimension table with parsed outcome prices and structured identifiers",
        primary_key=["market_id"],
        indexes=[["condition_id"], ["slug"], ["closed"]],
        columns={
            "market_id": ("VARCHAR", "Unique numeric market ID"),
            "question": ("VARCHAR", "Market proposition title"),
            "condition_id": ("VARCHAR", "Gnosis CTF condition ID"),
            "slug": ("VARCHAR", "URL slug for market"),
            "resolution_source": ("VARCHAR", "Resolution source URL / text"),
            "closed": ("BOOLEAN", "Trading closed flag"),
            "active": ("BOOLEAN", "Market active flag"),
            "category": ("VARCHAR", "High-level market category tag"),
            "yes_price": ("DOUBLE", "Parsed YES outcome price"),
            "no_price": ("DOUBLE", "Parsed NO outcome price"),
            "clob_token_ids": ("VARCHAR[]", "Array of CLOB asset token IDs"),
            "start_date": ("TIMESTAMPTZ", "ISO8601 timestamp when trading officially opened on Polymarket"),
            "end_date": ("TIMESTAMPTZ", "ISO8601 scheduled market closing / question expiration date"),
            "closed_time": ("TIMESTAMPTZ", "ISO8601 timestamp when trading on Polymarket was closed"),
            "uma_end_date": ("TIMESTAMPTZ", "ISO8601 timestamp when UMA Oracle liveness expired / DVM vote completed and market formally resolved"),
            "uma_resolution_status": ("VARCHAR", "UMA Oracle status ('proposed', 'disputed', 'resolved')"),
            "uma_question_id": ("VARCHAR", "UMA Oracle question ID"),
            "resolved_by": ("VARCHAR", "UMA CTF Adapter smart contract address that resolved the market"),
            **get_dw_columns(),
        },
    ),
    TableConfig(
        name="clean_dc_threads",
        description="Clean dispute threads table with extracted market_id foreign keys",
        primary_key=["thread_id"],
        indexes=[["market_id"], ["author_username"]],
        columns={
            "thread_id": ("VARCHAR", "Discord thread ID"),
            "market_id": ("VARCHAR", "Extracted Polymarket market_id foreign key"),
            "author_username": ("VARCHAR", "Thread starter username"),
            "timestamp": ("TIMESTAMPTZ", "ISO8601 timestamp when the dispute thread was initiated in Discord #disputes"),
            "content": ("VARCHAR", "Thread starter text content"),
            **get_dw_columns(),
        },
    ),
    TableConfig(
        name="clean_dc_messages",
        description="Clean dispute messages table with extracted DVM vote stances (P1-P4)",
        primary_key=["message_id"],
        indexes=[["thread_id"], ["vote_type"]],
        columns={
            "message_id": ("VARCHAR", "Discord message ID"),
            "thread_id": ("VARCHAR", "Parent thread ID"),
            "author_username": ("VARCHAR", "Message author username"),
            "timestamp": ("TIMESTAMPTZ", "ISO8601 message timestamp"),
            "vote_type": ("VARCHAR", "Extracted vote stance ('P1', 'P2', 'P3', 'P4')"),
            **get_dw_columns(),
        },
    ),

    TableConfig(
        name="clean_ur_signals",
        description="Clean UMA DVM committee consensus signals",
        primary_key=["id"],
        indexes=[["round_id"]],
        columns={
            "id": ("VARCHAR", "Signal ID"),
            "question": ("VARCHAR", "Dispute question"),
            "ancillary_data": ("VARCHAR", "Raw ancillary data string"),
            "answer": ("VARCHAR", "Consensus answer ('P1', 'P2', 'P3', 'P4')"),
            "round_id": ("BIGINT", "DVM voting round ID"),
            "timestamp": ("BIGINT", "Unix timestamp"),
            "timestamp_iso": ("TIMESTAMPTZ", "ISO8601 UTC timestamp calculated from timestamp epoch"),
            "reward": ("DOUBLE", "Reward token amount"),
            **get_dw_columns(),
        },
    ),
]
