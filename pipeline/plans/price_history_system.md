# PM Price History — API Findings & Revised System

Companion to [v3_hybrid_calibration.md](v3_hybrid_calibration.md). Captures what we
verified empirically about the Polymarket price API, the schema changes already made,
and the revised dispute-windowed ingestion model (initial backfill + 5-min incremental).

The arb the product hunts is **PM trading price *during* a dispute vs predicted τ**.
So the only price span worth storing is the dispute window. Everything below follows
from that.

---

## 1. API findings (verified against the live API, not assumed)

### 1.1 `prices-history` returns the resampled MIDPOINT, not last-transacted
On a liquid mid-priced market: series point `p = 0.525`, midpoint = `0.525`, but
bid/ask = `0.52 / 0.53`. The point equals `(bid+ask)/2`, **not** the last fill.
There is no last-trade field on this endpoint.

> The original spec's `price = "last transacted"` is **not satisfiable** from this API.
> We store the midpoint and named the column honestly.

### 1.2 The timestamp is a resampled bar time, not a transaction time
Spacing is governed by `fidelity`, regardless of when trades happened:
- `fidelity=1` → ~60s bars
- `fidelity=5` → ~300s bars (the 5-min cadence we want)
- `fidelity=60` → ~3600s bars

> The original spec's `transacted_at` is misleading. We named the column
> **`observed_at`** (the API `t`, unix seconds).

### 1.3 Bid / ask / last-trade have NO historical endpoint
| endpoint | returns | historical? |
|---|---|---|
| `prices-history` | midpoint series (`t`,`p`) | ✅ the only one |
| `last-trade-price` | last fill + side | ❌ spot only (now) |
| `book` / `midpoint` / `price` / `spread` | bid/ask/mid snapshot | ❌ spot only (now) |
| `trades` | actual fills | 🔒 401 — needs L2 wallet-signed key |

> **Decision (confirmed):** use midpoint for all calculations. Bid/ask/last-trade
> cannot be backfilled and aren't needed for backtesting. Caveat for *live* execution
> only: you can't fill at the midpoint, so a real arb must also clear the half-spread —
> don't let backtest midpoint-optimism leak into live PnL assumptions.

### 1.4 5-min fidelity requires range mode and is capped at ~15 days
Two mutually exclusive modes on `prices-history`:

- **Range mode** (`startTs`/`endTs` given): the **only** mode that honors a fine
  `fidelity`. `interval` is ignored and is dropped by the connector. **Hard cap:**
  a span > ~15 days returns `400 "invalid filters: 'startTs' and 'endTs' interval is
  too long"` — at *every* fidelity (cap is span-based, not point-based).
- **Window mode** (no range): `interval` (`max|all|1m|1w|1d|6h|1h`) drives the span,
  but over a long window the API **silently coarsens** fidelity
  (`interval=max` + `fidelity=5` → ~10-min bars, not 5-min).

> So "entire history at 5-min" is impossible in one call. But the dispute window is
> short (see §1.5), so it fits in a single range call. Chunking into ≤14-day windows
> is only a **fallback** for the rare dispute open > 15 days.

### 1.5 The resolution timestamp is an API field — no on-chain lookup needed
The Gamma market payload carries `umaEndDate` and `closedTime`:
- On resolved markets they are **identical** and **100% populated** (40/40 sampled).
- They line up with where the price series ends (Δ ≈ 0h).
- Both are **null while the dispute is in-progress**.

> `umaEndDate` (≡ `closedTime`) **is** the dispute-resolved moment = the END bound of
> the price window. No fixed-window guess, no subgraph plumbing required.

---

## 2. The dispute price window

For a market linked to a dispute thread:

```
window_start = thread_open_time − 1 day      (1-day pre-dispute buffer, confirmed)
window_end   = uma_end_date  if resolved     (≡ closed_time)
             = now           if in-progress  (uma_end_date IS NULL)
```

- Price *before* the dispute = irrelevant baseline (the 1-day buffer is just context).
- Price *after* resolution = flatlines at 0/1 (CTF adapter has mechanically settled).
- Dispute cycle (liveness + commit/reveal, occasionally a rolled vote) runs ~2–4 days
  — **well under the 15-day range cap**, so one range call per token covers it.

---

## 3. Schema & connector changes already made

**`raw_pm_price_history`** (new table, [db_schema.py](../src/db_schema.py)):
- `clob_token_id TEXT`, `price REAL` (midpoint), `observed_at INTEGER` (unix sec), + dw cols.
- Composite **PK `(clob_token_id, observed_at)`** → append-on-cadence (Phase 5).
  Re-fetching a boundary bar upserts in place; a true duplicate cannot exist.
- Indexed on `clob_token_id` and `observed_at`.

**`raw_pm_markets`** gained `closed_time` + `uma_end_date` (TEXT) — the resolution
timestamps from §1.5. Mirrored on the `PolymarketMarket` model (`closedTime`/`umaEndDate`).

**`ClobClient.get_prices_history`** ([polymarket.py](../src/connectors/polymarket.py)):
- Range mode vs window mode (§1.4); drops `interval` when a range is passed.
- `MAX_RANGE_WINDOW_SEC = 15d` documented as the chunking bound.

**`backfill_pm_price_history()`** + `_upsert_price_history()` ([batch_seed.py](../src/batch_seed.py)):
- Currently fetches per-token midpoint series and composite-PK upserts.
- **TODO (not yet written):** rewrite to be dispute-windowed + incremental + chunked
  per §4 and §5.

---

## 4. Initial dataset generation (backtesting)

1. **Get all dispute threads + messages.** Already ingested: `raw_dc_threads` /
   `raw_dc_messages` → `clean_dc_threads` / `clean_dc_messages`.
2. **Match each thread to its PM market.** `clean_dc_threads.market_id → raw_pm_markets.id`.
   `backfill_missing_markets()` fills gaps for markets referenced by threads but not yet
   pulled (uses the single-resource endpoint that returns archived markets).
3. **Resolved markets:** pull price history over `[thread_open − 1d, uma_end_date]`,
   **fidelity=1 (60s bars)**, range mode. Single call unless the window > 15d (then
   chunk, §5.3).
4. **Active markets:** pull over `[thread_open − 1d, now]`, same settings.

> **Fidelity decision (current):** start at **1-min** for simplicity — one clean
> range-call path, no extra moving parts. Per-trade (sub-minute) data is deferred to a
> separate high-fidelity table fed by the incremental loop once the system is running
> (§7). 5-min vs 1-min is a one-arg change if we revisit.

**X. User calibration profiles (separate track).** Compute from each user's comment
vote history vs the market's resolution (final settled prices at the resolution date).
This is Phase 2 of [v3_hybrid_calibration.md](v3_hybrid_calibration.md) — the
`discord_user_profiles` view — and is independent of price-history ingestion. Note the
lookahead trap (that plan, §Phase 5): for an *honest* backtest the accuracy weight must
be as-of T, not baked with future resolutions.

> Scope: this runs over the **disputed set** (distinct `market_id` in `clean_dc_threads`,
> ~few thousand historically), 2 tokens each (YES+NO). Not all 11k markets.

---

## 5. Incremental, every 5 minutes (revised — no watch-list)

**Key simplification (your insight):** disputed markets **auto-close themselves**, so we
don't need an explicit `WATCHED` state machine. The rule is implicit:

> A dispute is **live** while its market's `uma_end_date IS NULL`.
> Pull its price history each cycle until that flips; then do one final bounded pull and freeze.

The "disputed set" = distinct `market_id` present in `clean_dc_threads`. That set
*replaces* the watch-list. "Live" = that set filtered to `uma_end_date IS NULL`.

### 5.1 The loop

1. **Detect new dispute threads.** Discord incremental pull (existing `run_incremental
   discord`) appends new `#disputes` threads → new `market_id`s enter the disputed set.

2. **Refresh market metadata for the LIVE subset.** Re-fetch Gamma metadata for disputed
   markets where `uma_end_date IS NULL` (plus any brand-new market_ids from step 1).
   This is a small set — only the handful of disputes currently open, not thousands.
   Upsert `closed`, `uma_resolution_status`, `uma_end_date`, `clob_token_ids` into
   `raw_pm_markets`. **This is what detects a close transition** (`uma_end_date` goes
   null → set).

3. **Incremental price pull for each live (and just-closed-this-cycle) market.**
   For each YES/NO token:
   - `start_ts = MAX(observed_at) stored for that token` (the gap-fill start), else
     `thread_open − 1d` on first sight.
   - `end_ts = uma_end_date if just resolved, else now`.
   - One range call (the gap is ~5 min, so never near the 15d cap), composite-PK upsert.

4. **Freeze the resolved.** Once a market has `uma_end_date` set **and** has been pulled
   through that end, it leaves the live subset and is no longer queried. No explicit
   state write needed — the `uma_end_date IS NULL` filter does it.

### 5.2 Why this is cheap and self-bounding
- Metadata refresh + price pull touch only **currently-open disputes** (a handful), not
  the full disputed history.
- Append volume = `2 tokens × few live disputes × 5-min ticks over a ~2–4 day window`
  — trivial in SQLite.
- No watch-list table, no transition function — `uma_end_date IS NULL` is the entire
  state machine.

### 5.3 Where chunking still matters
Only the **initial backfill** (§4) of a dispute already open > 15 days needs to walk the
window in ≤14-day chunks. The 5-min incremental never hits the cap (its gap is one tick),
so it stays a single call.

---

## 6. Open items / edge cases

- **"Closed then disputed" ordering.** Confirm PM status semantics for a market that
  closed and was *then* disputed — could it slip the disputed-set filter? (Carried over
  from v3 plan TODO.)
- **P3 / 50-50 resolution** (`["0.5","0.5"]`): the post-resolution series won't pin to
  0/1 — handle in calibration grading, not here.
- **`uma_end_date` present but series not yet flatlined** at the moment of the cycle:
  benign — the final-bound pull captures whatever exists; next cycle the market is frozen.
- **Settlement value vs midpoint** for grading: calibration (track X) should grade on the
  **settled outcome** (DVM revealed price / final 0–1), not the midpoint series.

---

## 7. DEFERRED: per-trade price (`raw_pm_trades`), high-fidelity table

**Status: deferred.** Ship 1-min midpoint (§4) first; add this once the system runs.
Motivation: align exact price moves to timestamped Discord voter messages — does price
react within seconds of a voter telegraphing their lean. A 60s bar smears any reaction
faster than a minute, which is exactly the front-running window. That needs per-fill data.

### 7.1 Source (verified live, 2026-06)
`https://data-api.polymarket.com/trades?market=<conditionId>` — public, no auth.
(NOTE: `clob.polymarket.com/trades` is a different, 401-walled endpoint — use the
`data-api` host.) Returns individual fills: `timestamp` (unix sec), `price`, `size`,
`side`, `outcome`/`outcomeIndex`, `asset` (=clob_token_id), `conditionId`,
`proxyWallet`, `transactionHash`. Sub-second resolution is real (many trades share a
second). See [[polymarket-trades-api]].

### 7.2 Two hard limits that shaped the deferral
- **`offset` caps at ~4000** (offset ≥ 3999 → HTTP 400). Newest-first. So **at most the
  ~4000 most-recent trades per market are retrievable** via this path; older fills are
  unreachable. For a resolved dispute the newest ≈ the resolution tail, so the reachable
  4000 covers the window's end — but a long/busy dispute loses its early hours.
- **All time params are ignored** (`startTs`/`endTs`/`before`/`after`/… all return the
  newest N). No server-side windowing — page by `offset` and filter `timestamp`
  client-side, walking back until past `thread_open − 1d`.

### 7.3 Volume & storage estimate (2,009 disputed markets, stratified by PM volume)
| band | # markets | avg trades/mkt (measured) | band total |
|---|---|---|---|
| <1k | 596 | ~30 (est.) | ~18k |
| 1k–50k | 761 | 420 | ~320k |
| 50k–500k | 357 | 1,533 | ~547k |
| 500k–5M | 191 | 2,797 | ~534k |
| >5M | 104 | 3,451 (cap-truncated) | ~359k+ |

**≈ 1.7–1.8M retrievable trade rows.** At ~150–200 B/row trimmed (asset, timestamp,
price, size, side, condition_id, transaction_hash) ≈ **~0.5 GB** table+indexes in SQLite.
Backfill ≈ 1,800 paged calls + 2,009 first-calls ≈ ~3,800 requests one-time (~2 min at
300 req/10s). PK `transaction_hash` (or `(transaction_hash, asset)`) for dedup.

### 7.4 The whale gap & its escape
The ~104 markets in the >5M band genuinely have far more than 4000 fills — the bulk of
the sentiment-arb signal — and `data-api` can't reach the older ones. The clean escape is
the **on-chain trades subgraph** (`reference/subgraphs/`, `OrderFilled`/`OrdersMatched`):
no offset cap, full history, but a separate ingestion path. Pursue only if whale
completeness matters for the backtest.

### 7.5 The sentiment primitive (why this table exists)
Join `clean_dc_messages.timestamp` against `raw_pm_trades.timestamp` per dispute: "did
price move within N seconds of this voter's message." This is the higher-resolution
signal the midpoint bars can't express. Trade `price` carries bid/ask bounce (a fill, not
a midpoint) — fine for *timing* pressure, but do NOT mix it into the midpoint price axis
used for τ vs price arb.
