# Polydispute Frontend & Intelligence Engine Plan

## 1. Executive Summary & Alpha Thesis

Polydispute is an automated intelligence and arbitrage engine designed to detect, track, and capitalize on pricing inefficiencies in Polymarket prediction markets subject to UMA Optimistic Oracle disputes.

### The Core Inefficiency
1. **Resolution Mechanism**: Disputed Polymarket markets are decided on-chain by UMA DVM (Data Verification Mechanism) tokenholders over a 24–48 hour commit-reveal cycle.
2. **Orderbook Lag**: During active disputes, Polymarket orderbook prices frequently suffer from information lag, thin liquidity, panic selling, or confusion over UMA protocol edge cases.
3. **Leading Signal in Discord**: Protocol analysts, forecasters, and UMA token stakers debate evidence in the official UMA Discord `#disputes` channel hours before on-chain commit-reveal.
4. **The Arbitrage**: By calibration-weighting Discord dispute consensus in real-time, we compute a synthetic **Crowd-Implied Expected Value** that leads the orderbook price and highlights tradeable mispricings.

---

## 2. Mathematical Framework & Calibration Engine

### A. Entity Centralization on `market_id` (Latest Vote per User)
Since Discord is our sole crowdsourced intelligence source, the entire engine centralizes strictly on **`market_id`** (not `thread_id`):
- **Cross-Thread Stance Aggregation**: If multiple threads exist for the same market, each user's stance on that market is defined by their **most recent vote (`P1`, `P2`, `P3`, `P4`)** across all linked threads.
- **Deduplication**: Each unique user contributes **exactly 1 active vote** to the market's live EV and is graded **exactly 1 time per market** on the calibration leaderboard.

### B. Bayesian Voter Accuracy Score (S_u)
Raw vote counts are distorted by noisy or uncalibrated retail participants. Each voter's reliability is scored using an Empirical Bayes prior:

```
S_u = (Prior_P * N + Correct_Predictions) / (N + Gradeable_Predictions)
```
- **Prior Score (P = 0.50)**: Default accuracy prior for uncalibrated/new voters.
- **Trust Number (N = 20)**: Sample size threshold required to pull a voter away from the prior.
- **Decisive Grading Only**: Only markets resolving decisively (`yes_price >= 0.99` or `no_price >= 0.99`) count toward voter calibration. 50-50 / Cancelled markets are excluded from penalizing voters.

### C. Exponential Power Weighting Function (W_u)
To reward elite forecasters and suppress low-accuracy noise, voter power weights scale exponentially:

```
Weight (W_u) = (S_u)^p
```
- **Quadratic Scaling (S^2, Default)**: An 80% accurate voter receives `(0.80)^2 = 0.64` weight, which is **4.0x** the voting power of a 40% accurate voter `(0.40)^2 = 0.16`.

### C. Option 2 Point-in-Time Terminal Payoff Vector
Under Polymarket's Conditional Tokens Framework (CTF), each discrete vote outcome has a deterministic terminal payoff:

| Vote Stance | Meaning | Terminal Payoff Contribution |
| :--- | :--- | :--- |
| **P1** | `NO` | **$0.00** |
| **P2** | `YES` | **$1.00** |
| **P3** | `50-50` (Ambiguous / Equal Split) | **$0.50** |
| **P4** | `Too Early` (Premature Proposal Rejection) | **P_market(t_vote)** (Point-in-time YES price before vote) |

#### Why Option 2 Point-in-Time for P4:
- P4 does not resolve the market; it rejects the immediate proposal as premature, returning the contract to open trading.
- Each voter casting P4 injects their observed market baseline price `P_market(t_vote)`, accurately capturing status-quo reversion and preventing false "Buy YES" arbitrage alarms.

### D. Implied Settlement Expected Value Formula
At any time `t` across all active voters:

```
Implied EV(t) = SUM(W_u * Payoff_u(t)) / SUM(W_u)
```

### E. Polarized Arbitrage Spread (Δ)
Measures the directional trading edge between the Crowd-Implied Settlement EV and the Polymarket Orderbook Price:

```
If Implied EV > 0.50 (Crowd leans YES):
    Spread Δ = Implied EV - Polymarket YES Price
    Action: BUY YES when Δ > 0 (Underpriced YES)

If Implied EV < 0.50 (Crowd leans NO):
    Spread Δ = Polymarket YES Price - Implied EV
    Action: BUY NO when Δ > 0 (Overpriced YES / Underpriced NO)

If Implied EV == 0.50 (Neutral / Ambiguous):
    Spread Δ = 0.00 (No directional edge)
```

### F. Temporal Dispute Round Clustering (Δt > 36h)
Duplicate Discord discussion threads created for the same market within hours are grouped into the same dispute round. Gaps `> 36 hours` indicate genuine multi-round disputes (e.g. Round 1 vs. Round 2).

### G. Ground Truth Resolution Rules (Source A)
Ground truth is strictly derived from Polymarket terminal settlement prices:
```
* P2 (YES):   yes_price >= 0.99 (or closed resolved with yes_price > 0.60)
* P1 (NO):    no_price >= 0.99 or yes_price <= 0.01 (or closed resolved with yes_price < 0.40)
* P3 (50-50): 0.48 <= yes_price <= 0.52 and closed/resolved
* Pending:    Market remains open / unclosed
```

---

## 3. Current Implementation Status (`frontend/dev_ui.py`)

The prototype Streamlit SPA devtool is operational and provides:

1. **Section 1: Aggregate Dispute Outcome Accuracy Benchmark**:
   - Evaluates all historical resolved disputes against Source A ground truth.
   - Computes Predominant Plurality Win Rate and Weighted EV Implied Win Rate.
   - Interactive confusion breakdown table.
2. **Section 2: Disputed Threads & Arbitrage Screener Catalog**:
   - Interactive table with single-row click selection.
   - Columns: `market_id`, `question`, `ground_truth`, `UR Committee Submit`, `yes_price`, `crowd_ev`, `arb_spread_cents`, `arb_action`, `total_votes`, `total_rounds`.
   - Filters: Search, Status, `🟢 Arbitrage Only (Spread > 0)`, `Min Votes`.
   - Auto-sorted by highest positive arbitrage spread descending.
3. **Section 3: Market Deep-Dive & Trajectory Charts**:
   - **Chart 1: Full Lifecycle Price History**: Polymarket price from inception to resolution with strict `≤ 48h` shaded dispute zones.
   - **Chart 2: Dual-Axis Dispute Window Breakdown**: Solid weighted lines vs. dashed raw lines for P1/P2/P3/P4 vote share.
   - **Chart 3: 3-Line Unified Arbitrage Graph ($0.00–$1.00 scale)**:
     - Solid Bold Green: Calibration-Weighted Implied EV.
     - Dashed Orange: Raw Unweighted Implied EV.
     - Solid Thin Black: Polymarket Orderbook YES Price.
     - Real-time Arbitrage Action metric cards and callout alerts.
4. **Tab 2: Voter Calibration Leaderboard**:
   - Bayesian vs. Raw Accuracy ranking table and Top 15 comparative bar chart.
5. **Tab 3: Methodology, Theory & Backtest Validation**:
   - Complete documentation of equations, mechanics, empirical win rates, and structural risk disclosures.

---

## 4. Productization Architecture Roadmap

```
+---------------------------------------------------------------------------------------+
| ARCHITECTURE FOR PRODUCTION                                                           |
|                                                                                       |
|  [ MotherDuck Warehouse ]                                                             |
|           │                                                                           |
|           ▼                                                                           |
|  [ FastAPI Backend (Python 3.12) ]                                                     |
|    - Exposes REST endpoints: /api/markets, /api/market/{id}/trajectory, /api/leaderboard|
|    - Caches Bayesian weights and market aggregations in Redis                         |
|           │                                                                           |
|           ▼                                                                           |
|  [ Next.js 14 Frontend (React / Tailwind / TradingView Lightweight Charts) ]         |
|    - Real-time interactive UI hosted on Coolify                                      |
|    - Direct browser query to Polymarket CLOB API for live top-of-book depth & spread  |
+---------------------------------------------------------------------------------------+
```

### Direct Client-Side CLOB Depth Architecture
- Rather than snapshotting orderbooks every 5 minutes into MotherDuck, the frontend fetches live depth directly from Polymarket's public CLOB REST API (`https://clob.polymarket.com/book?token_id=...`).
- Guarantees zero database storage bloat and sub-second live spread precision on user deep-dive.

---

## 5. Live Intelligence & LLM Roadmap (Combined Features 1 & 3)

### Concept: Automated Legal Assessment & Live News Feed Engine
A dedicated intelligence panel in the market deep-dive combining contract fine print analysis and real-time evidence verification.

```
┌───────────────────────────────────────────────────────────────────────────────────────┐
│ AI DISPUTE INTELLIGENCE PANEL                                                         │
│                                                                                       │
│ 1. Contract Fine-Print Resolution Criteria                                            │
│    - Parsed directly from `clean_pm_markets.description`.                             │
│    - Highlights key clauses: Deadlines, official source URLs, exclusion conditions.   │
│                                                                                       │
│ 2. Evidence & News Feed (Extracted from Discord Embeds & URLs)                        │
│    - Scrapes headlines and article summaries from `clean_dc_messages.urls`.           │
│    - AI Stance Classification:                                                        │
│      [🟢 Bullish YES: Official statement meets rule #2]                               │
│      [🔴 Bullish NO: Announcement occurred after deadline]                            │
│      [🟡 Ambiguity Warning: Source URL returns 404 / conflicting reports]             │
│                                                                                       │
│ 3. LLM Legal Synthesizer Assessment                                                   │
│    - Summarizes the core debate arguments.                                            │
│    - Outputs an AI Confidence Score: e.g., "85% Likelihood of P1 (NO) ruling".        │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Upstream Data Quality & Validation Checklist

Before scheduling continuous 5-minute pipeline runs in Prefect, ensure the following database validations pass:

| Table | Required Field | Quality Rule / Constraint |
| :--- | :--- | :--- |
| **`clean_pm_markets`** | `market_id` | Primary Key; must be non-null and unique. |
| **`clean_pm_markets`** | `description` | Must retain full text resolution criteria from `raw_pm_markets`. |
| **`clean_pm_markets`** | `yes_price`, `no_price` | Floating point in `[0.0, 1.0]`; `yes_price + no_price ≈ 1.0`. |
| **`clean_dc_threads`** | `market_id` | Foreign Key linked to `clean_pm_markets.market_id`. |
| **`clean_dc_messages`** | `vote_type` | Must be strictly in `('P1', 'P2', 'P3', 'P4')`. |
| **`clean_dc_messages`** | `urls` | Extracted array of valid `http/https` strings. |
| **`clean_dc_messages`** | `author_username` | Admin bots (`UMA Herald`, `UMA Heralds`) must be excluded from vote tallies. |
| **`raw_pm_price_history`**| `observed_at_iso` | Monotonically increasing timestamps per `market_id`. |
| **`clean_ur_signals`** | `answer` | Mapped to standardized stances (`P1`, `P2`, `P3`, `P4`). |
