# Polydispute V3 Hybrid Calibration Plan

This plan details the end-to-end implementation for ingesting the UMA Rocks anchor (Tier 1) and calculating the historical accuracy of Discord users (Tier 2) to compute the final `Tau` edge in our data warehouse.

As requested, this isolates the work entirely within the pipeline layer. Backend API updates will be done later once the data is verified.

## Phase 1: Ingesting UMA Rocks (Tier 1 Anchor)

We will ingest the `getPoolAnswers` API to establish the baseline 22% anchor for the `Tau` engine.

**1. Create Connector (`pipeline/src/connectors/uma_rocks.py`)**
```python
import requests
from loguru import logger
from typing import List, Dict, Any

class UMARocksClient:
    API_URL = "https://www.uma.rocks/api/getPoolAnswers"
    
    def get_pool_answers(self) -> List[Dict[str, Any]]:
        logger.info(f"Fetching from {self.API_URL}")
        try:
            response = requests.get(self.API_URL, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch UMA Rocks API: {e}")
            return []
```

**2. Update Schema (`pipeline/src/db_schema.py`)**
```python
TableConfig(
    name="raw_uma_rocks_signals",
    columns={
        "id": "TEXT PRIMARY KEY", # Synthetic ID or from the payload
        "question": "TEXT",
        "ancillaryData": "TEXT",
        "time": "INTEGER",
        "reward": "REAL",
        **get_dw_columns()
    }
)
```

**3. Pipeline Execution (`pipeline/src/pull_api.py`)**
- Add an ingestion flow in `pull_api.py` (during the `run_sync()` loop) to poll `UMARocksClient().get_pool_answers()` and dump JSON results into `raw_uma_rocks_signals`.

---

## Phase 2: Dynamic Voter Calibration (Tier 2 Social)

We will use a stateless SQLite `VIEW` to compute `discord_user_profiles` dynamically. 
To ease in new users and filter noise, we ignore uncalibrated users who haven't hit a `MIN_CALIBRATION_VOTES` threshold.

**1. Add Configuration (`pipeline/src/config.py`)**
```python
class PipelineConfig:
    # ... existing configs ...
    MIN_CALIBRATION_VOTES = 5  # Users with < 5 votes have 0 weight
```

**2. Transform Layer (`pipeline/src/transform.py`)**
We will add a new function `create_user_profiles_view()` right before `create_disputes_view()`.

```python
def create_user_profiles_view() -> None:
    logger.info("Creating discord_user_profiles view...")
    conn = get_sqlite_conn()
    
    view_sql = """
    CREATE VIEW discord_user_profiles AS
    SELECT 
        v.author_username,
        COUNT(v.message_id) AS total_predictions,
        SUM(
            CASE 
                -- P1 corresponds to YES (yes_price = 1.0)
                WHEN m.yes_price = 1.0 AND v.vote_type = 'P1' THEN 1
                -- P2 corresponds to NO (no_price = 1.0)
                WHEN m.no_price = 1.0 AND v.vote_type = 'P2' THEN 1
                ELSE 0
            END
        ) AS correct_predictions,
        CAST(SUM(
            CASE 
                WHEN m.yes_price = 1.0 AND v.vote_type = 'P1' THEN 1
                WHEN m.no_price = 1.0 AND v.vote_type = 'P2' THEN 1
                ELSE 0
            END
        ) AS REAL) / COUNT(v.message_id) AS lifetime_accuracy
    FROM clean_dc_messages v
    JOIN clean_dc_threads t ON v.thread_id = t.thread_id
    JOIN clean_pm_markets m ON t.market_id = m.market_id
    WHERE m.uma_resolution_status = 'resolved'
    GROUP BY v.author_username;
    """
    
    conn.execute("DROP VIEW IF EXISTS discord_user_profiles")
    conn.execute(view_sql)
    conn.commit()
    conn.close()
```

> ### ⚠️ Fix: exclude P3/P4 from the accuracy denominator
> The view above computes `lifetime_accuracy = correct / COUNT(message_id)` — every vote, including P3 (Unknown) and P4 (too-early). A user who correctly calls P4 on a fresh dispute is *right*, but P4 can never match a final YES/NO resolution, so it counts in the denominator and never in the numerator — silently dragging accuracy down and punishing exactly the cautious, early-signalling users we most want to weight. The denominator must count only **resolvable directional votes (P1/P2)**:
>
> ```sql
> -- denominator: only graded P1/P2 votes, not P3/P4
> COUNT(CASE WHEN v.vote_type IN ('P1','P2') THEN 1 END) AS gradeable_predictions,
> CAST(SUM(CASE
>     WHEN m.yes_price = 1.0 AND v.vote_type = 'P2' THEN 1   -- P2 = YES
>     WHEN m.no_price  = 1.0 AND v.vote_type = 'P1' THEN 1   -- P1 = NO
>     ELSE 0 END) AS REAL)
>   / NULLIF(COUNT(CASE WHEN v.vote_type IN ('P1','P2') THEN 1 END), 0) AS lifetime_accuracy
> ```
>
> Note `NULLIF(..., 0)` guards the divide-by-zero for users who only ever posted P3/P4. Also fix the P1/P2↔YES/NO mapping: P2 = YES (`yes_price = 1.0`), P1 = NO (`no_price = 1.0`) — the original draft had this inverted.
>
> **PM settled price IS the ground truth (resolved: not a concern).** We only grade users on disputes where `uma_resolution_status = 'resolved'`. At that point the Polymarket CTF adapter has *mechanically settled* the market from the DVM's resolved price — PM settlement is downstream of the DVM vote, not a traded consensus. So the settled price equals the DVM outcome by construction; using it as ground truth is correct, not circular. (The arb the product hunts is between the PM *trading* price *during* the dispute and predicted τ — a different quantity from the settled price.) Two data-hygiene caveats remain: use `yes_price > 0.99` instead of exact `= 1.0` (settlement may report `0.9999`), and confirm handling of P3/50-50 resolutions (`["0.5","0.5"]` matches neither branch).

---

## Phase 3: The Tau Engine (`disputes_view`)

We rewrite `create_disputes_view()` to calculate `weighted_p1` and `weighted_p2`. We apply the rule: if `total_predictions` < `MIN_CALIBRATION_VOTES`, their weight is `0.0`.

```python
from config import PipelineConfig

def create_disputes_view() -> None:
    conn = get_sqlite_conn()
    
    # We join clean_dc_messages against discord_user_profiles
    # and sum their lifetime_accuracy if they pass the threshold.
    view_sql = f"""
    CREATE VIEW disputes_view AS
    SELECT 
        t.thread_id,
        m.condition_id,
        m.question,
        m.slug,
        m.uma_resolution_status,
        m.uma_bond,
        m.uma_reward,
        m.neg_risk,
        m.yes_price,
        m.no_price,
        
        -- Raw counts
        COUNT(CASE WHEN v.vote_type = 'P1' THEN 1 END) AS p1_votes,
        COUNT(CASE WHEN v.vote_type = 'P2' THEN 1 END) AS p2_votes,
        
        -- Weighted scores (Tier 2 Math)
        SUM(
            CASE 
                WHEN v.vote_type = 'P1' AND COALESCE(u.total_predictions, 0) >= {PipelineConfig.MIN_CALIBRATION_VOTES} 
                THEN u.lifetime_accuracy 
                ELSE 0 
            END
        ) AS weighted_p1_votes,
        SUM(
            CASE 
                WHEN v.vote_type = 'P2' AND COALESCE(u.total_predictions, 0) >= {PipelineConfig.MIN_CALIBRATION_VOTES} 
                THEN u.lifetime_accuracy 
                ELSE 0 
            END
        ) AS weighted_p2_votes,
        
        p.ancillary_data_decoded
    FROM clean_dc_threads t
    JOIN clean_pm_markets m ON t.market_id = m.market_id
    LEFT JOIN clean_dc_messages v ON t.thread_id = v.thread_id
    LEFT JOIN discord_user_profiles u ON v.author_username = u.author_username
    LEFT JOIN clean_polygon_ancillary p ON m.uma_question_id = p.uma_question_id
    GROUP BY t.thread_id;
    """
    
    conn.execute("DROP VIEW IF EXISTS disputes_view")
    conn.execute(view_sql)
    conn.commit()
    conn.close()
```

## Phase 4: Tau Computation (Resolution Plan)

> Previously deferred. This is the core deliverable: without it there is no `tau` and no `arb_spread` — the two columns the product exists to show. The plan below resolves four gaps: (A) the missing bridge join, (B) the undefined formula, (C) the wrong join key, (D) — handled back in Phase 2 — the accuracy denominator.

### 4A. Bridge join — UMA Rocks ↔ Polymarket (use the hash, not fuzzy text)

The signal is currently stranded: `raw_uma_rocks_signals` has no key into `clean_pm_markets`. Fuzzy question-string matching is fragile (truncation, punctuation, "Will X?" vs "Will X happen?"). The robust key already exists (`reference/notes/voting-sources.md:434`):

- The UMA Rocks `ancillaryData` payload contains an **`ancillaryDataHash`** = `keccak256` of the Polygon-side `ancillaryData`.
- We already store that Polygon-side `ancillaryData` as `ancillary_data_hex` in `raw_polygon_ancillary`.

**Join = `keccak256(polygon ancillary_data_hex bytes) == ancillaryDataHash parsed from the UMA Rocks payload`.**

Schema gap to fix first: `clean_polygon_ancillary` **drops the hex** (keeps only `uma_question_id`, `oracle_version`, `ancillary_data_decoded`). So either:
1. propagate `ancillary_data_hex` into `clean_polygon_ancillary`, OR
2. compute the hash at transform time and store it as a dedicated `ancillary_data_hash` column (preferred — join on a precomputed indexed hash, not a recomputed one).

Implementation steps:
- [ ] Add `ancillary_data_hash` (`TEXT`) to `clean_polygon_ancillary`; populate via `keccak256` of the raw hex during `transform_polygon_ancillary()`. Index it.
- [ ] Parse `ancillaryDataHash` out of the UMA Rocks `ancillaryData` blob in a new `clean_uma_rocks_signals` transform; store as `ancillary_data_hash`.
- [ ] Join `clean_uma_rocks_signals` → `clean_pm_markets` via `ancillary_data_hash → uma_question_id` (through `clean_polygon_ancillary`).
- [ ] **Fallback only:** if hash is absent/unparseable, fuzzy-match `question`. Log every fallback — a high fallback rate means the hash parse is broken.
- [ ] **Cross-chain trap** (`voting-sources.md:445`): when ancillaryData bridges Polygon→Ethereum it is keccak-hashed; the subgraph field carries an `ancillaryDataHash:` prefix. Match on `identifier` + `time` as a secondary fallback.

### 4B. Tau formula — normalize the social term, clamp to [0,1]

The stated formula `Tau = (Tier 1 Base) ± (Weighted Sum of Tier 2)` is dimensionally broken: it adds a probability (~0.995 in a direction) to an **unbounded** sum of accuracy scores. With 3 users that sum ≈ 2.5; with 40 users ≈ 30 — tau explodes past 1.0 and the number is meaningless. The magnitude of the social shift cannot scale with crowd size; it must scale with **net weighted conviction**.

Define tau on the YES axis (`tau_yes ∈ [0,1]`), with a tunable social influence cap `λ` (e.g. 0.15 — Tier 1 is the anchor, Tier 2 nudges):

```
# Tier 1 anchor: UMA Rocks answer → base probability
base = 0.995 if answer == P2 (YES) else 0.005   # P1 = NO

# Tier 2 social shift: NORMALIZED net lean, not a raw sum
#   weighted_p2_votes / weighted_p1_votes already come from disputes_view (Phase 3),
#   each user's vote weighted by lifetime_accuracy, gated by MIN_CALIBRATION_VOTES.
W = weighted_p2_votes + weighted_p1_votes
social_lean = (weighted_p2_votes - weighted_p1_votes) / W   if W > 0 else 0.0   # ∈ [-1, +1]

# Combine, then CLAMP
tau_yes = clamp(base + λ * social_lean, 0.0, 1.0)

arb_spread = abs(pm_price_yes - tau_yes)
```

Properties this guarantees:
- `social_lean` is bounded in `[-1, +1]` regardless of crowd size — 3 unanimous users and 40 unanimous users both yield ±1; magnitude reflects *agreement*, not *headcount*.
- `λ` caps how far Tier 2 can move the Tier 1 anchor; tune by backtest.
- `clamp` guarantees a valid probability.
- When `W = 0` (no calibrated voters), tau = the pure Tier 1 anchor — the correct degenerate case.

Steps:
- [ ] Implement in the compute layer (a `compute_arb_signals()` step, run per cron cycle after transforms — see Phase 5 cadence). Not `app.py`: the value must be **snapshotted** into `arb_signals`, not computed on read, or there is no history (Phase 5).
- [ ] Add `λ` and the `P2 = YES / P1 = NO` mapping to `config.py`.
- [ ] Backtest `λ` against resolved disputes once the as-of price series exists.

### 4C. Output

`compute_arb_signals()` writes one append-on-cadence row per WATCHED market per cycle into `arb_signals` (`condition_id`, `captured_at`, `pm_price_yes`, `tau_yes`, `arb_spread`). `tau_yes` is nullable for the pre-join window (price exists before UMA Rocks answers). The dashboard reads the latest row for live, as-of rows for backtest.

### Backend Integration (Phase 4 → API, still deferred)
Once `arb_signals` is populated and verified, wire `app.py` to serve it and the Discord X-Ray ledger. The math now lives in the pipeline, so the API only reads.

---

## Phase 5: Data Persistence Model (View vs Materialize)

The core decision is **not per-table**. It is two questions asked of every *value*:

1. **Does it mutate?** (does the source change it after first write)
2. **Do I need its past?** (is a historical cross-section required for the dashboard or backtest)

A `VIEW` can only ever show *now* — it recomputes from whatever the underlying tables currently hold. Because `load_json_to_table()` upserts (`ON CONFLICT DO UPDATE`), those tables hold only the latest value; the past is already overwritten. **Therefore no view can reconstruct a past cross-section.** History must be captured at write time, in an append-only table. This is why a live dashboard built purely on views cannot be backtested.

### The five persistence modes

| Mode | Mechanism | Use when |
|---|---|---|
| **Append-only log (immutable)** | plain `INSERT`; natural source ID is PK | source emits immutable events (Discord messages). Not "tracked over time" — it *is* the log. PK dedups re-fetch overlap. |
| **Latest-only (upsert)** | `ON CONFLICT(pk) DO UPDATE` | value mutates but only *now* matters, OR value is immutable and fetched once. |
| **View** | no storage; recomputed at read time | value is purely derived and only *now* matters. |
| **Append-on-cadence** | one row per entity **per cron run**, unconditional; PK `(entity, captured_at)` | value moves ~continuously (price). Even spacing makes the as-of backtest query trivial. |
| **Append-on-change** | read last row; `INSERT` only if value differs; PK `(entity, captured_at)` | value is a sparse discrete signal (UMA answer). Stores transitions, not N identical rows. |

### Per-value verdict

| Value | Table | Mutates? | Need past? | Mode | PK / dedup |
|---|---|---|---|---|---|
| Discord messages | `raw_dc_messages` | no (event) | — | append-only log | `message_id` |
| Discord threads | `raw_dc_threads` | no (event) | — | append-only log | `id` |
| Polygon ancillary (rules text) | `clean_polygon_ancillary` | no | no | latest-only (fetch once) | `uma_question_id` |
| PM yes/no price | **`market_price_history`** (new) | yes | **yes** | **append-on-cadence** | `(condition_id, captured_at)` |
| `closed` / `uma_resolution_status` | rides in `market_price_history` row | yes | yes | append-on-cadence | (same row as price) |
| PM live "current price" cell | `clean_pm_markets` | yes | no (history lives in series) | latest-only (upsert) | `condition_id` |
| UMA Rocks answer (P4→P1 flip) | **`uma_rocks_history`** (new) | rarely | **yes** (the flip *is* the event) | **append-on-change** | `(market_id, captured_at)` |
| `discord_user_profiles` (accuracy) | view | daily, on resolution | live: no* | view | — |
| `disputes_view` (live aggregation) | view | derived | no | view | — |
| Tau / arb_spread (the signal) | **`arb_signals`** (new) | derived | **yes** | **append-on-cadence** | `(condition_id, captured_at)` (`tau_yes` nullable pre-join) |

> We snapshot exactly **three** mutable things — price, UMA answer, computed tau — and only for watched markets (see Phase 6). Everything else stays a view or an immutable log. We do **not** make "all table types" append-only.

### Dedup is a non-problem

Every snapshot table uses composite PK `(entity_id, captured_at)`. Each cron tick has a distinct `captured_at`, so a true duplicate cannot exist by construction. The only real choice is **bloat suppression** — cadence (store every tick) vs change (store transitions). Dedup of *source* re-fetch overlap (e.g. the same Discord message pulled twice) is handled by the natural-ID PK on the raw log tables.

### Backtest primitive + the lookahead trap

Backtest = "what was known at T", an as-of read:

```sql
SELECT yes_price FROM market_price_history
WHERE condition_id = ? AND captured_at <= ?
ORDER BY captured_at DESC LIMIT 1;
```

The live dashboard is the same read with `T = now`. Live = views over latest; backtest = as-of over snapshots.

> \* **Lookahead trap on accuracy.** `discord_user_profiles.lifetime_accuracy` aggregates over *all* resolved disputes, including ones that resolved *after* the dispute being replayed. Backtesting a signal at T with weights that bake in future resolutions is data leakage. For an honest backtest, the weight must be as-of T — either snapshot the profile table over time too, or make the view parameterizable by an as-of date filtering resolutions to `< T`. For the *live* signal the plain view is fine.

---

## TODO: Discovery → Live Tracking Funnel

**Problem.** `run_sync()` currently syncs `closed = 0` — every open market on Polymarket (thousands), not disputes. Discovery finds markets by `start_date` within the watermark window, but disputes land on markets created weeks ago, so a start-date filter misses them. We need a per-market state machine that funnels the broad discovery set down to the handful of markets actually in dispute, and only those drive the 5-min snapshots.

### Target state machine

```
DISCOVERED ──dispute detected──▶ WATCHED ──resolves──▶ RESOLVED ──▶ accuracy backfill
```

- **DISCOVERED** — broad, slow cadence (hourly/daily). Wide date-window pull of new PM events. Does NOT need 5-min breadth.
- **Dispute detection (the filter into WATCHED)** — strongest signal first:
  - a `#disputes` thread linked to the market (`clean_dc_threads.market_id` present — near-decisive, the UMA bot opens exactly one on dispute), OR
  - market appears in `getPoolAnswers`, OR
  - `uma_resolution_status` in (`proposed`, `disputed`).
- **WATCHED** — 5-min sync, this subset only (a handful, not thousands). Drives all three snapshot writes (price, uma answer, tau) + the tau compute.
- **RESOLVED** — stop snapshotting, freeze the series, hand to the daily accuracy backfill (graded against **DVM revealed outcome**, not PM price — see open items).

### Storage

Add `watch_state` column on `clean_pm_markets` (or a small `watched_disputes` table). Discovery writes the state; live sync reads it. This funnel bounds append-only volume to **3 series × a few live disputes × a few hundred ticks** — trivial in SQLite, and exactly the granularity threshold tuning needs.

### Work items

- [ ] Replace `closed = 0` selector in `run_sync()` with the `WATCHED` subset.
- [ ] Add `watch_state` (`DISCOVERED` / `WATCHED` / `RESOLVED`) to the schema + a transition function.
- [ ] Split cron cadences: discovery (slow/broad) vs live sync (5-min/narrow).
- [ ] Implement dispute-detection filter (thread-link ∪ getPoolAnswers ∪ resolution_status).
- [ ] Define RESOLVED exit condition + trigger for accuracy backfill.
- [ ] Confirm PM status semantics for the edge case: a market that **closed and was then disputed** (could slip the funnel).
- [ ] Wire the three append-only writers (`market_price_history`, `uma_rocks_history`, `arb_signals`) to fire only for `WATCHED`.
