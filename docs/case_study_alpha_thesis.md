# Polydispute: Exploiting Information Lag in Prediction Market Dispute Oracles

**A Quantitative Case Study on Crowdsourced Bayesian Signal Extraction, Point-in-Time Payoff Modeling, and Serverless OLAP Architecture**

---

## Executive Summary

Prediction markets operate under the premise that price equals probability. However, when an outcome is contested and escalated to an on-chain dispute oracle (such as the **UMA Optimistic Oracle**), market pricing breaks down.

During the 24- to 48-hour commit-reveal dispute window, centralized orderbooks (e.g., Polymarket) frequently exhibit severe information lag, illiquidity, and panic mispricings. 

**Polydispute** is an automated analytical platform that monitors on-chain prediction disputes, scrapes real-time governance deliberations from private and public community channels, applies an **Empirical Bayes competency weighting engine**, and computes a leading synthetic Expected Value ($E[V]$) to surface structural arbitrage spreads ($\Delta$).

---

## 1. The Structural Inefficiency

### 1.1 The UMA Commit-Reveal Dispute Cycle
When an assertion on Polymarket is challenged, it escalates to the UMA Data Verification Mechanism (DVM):
1. **Challenge Phase**: A market proposal is disputed by staking a bond.
2. **Commit Window (24–48 hours)**: UMA tokenholders independently evaluate evidence and submit encrypted cryptographic commitments of their votes.
3. **Reveal Window (24 hours)**: Tokenholders reveal their votes on-chain.
4. **Settlement**: The smart contract tallies votes and settles the market decisively.

### 1.2 The Orderbook Lag
Throughout the 48-hour window, retail orderbook participants face massive uncertainty. Without visibility into commit hashes, retail traders panic-sell or anchor to stale sentiment. Meanwhile, protocol researchers, whale voters, and core contributors debate legalistic oracle edge cases in real-time within community discourse channels (specifically UMA Discord `#disputes`).

By systematically parsing and scoring this discourse, we observe the consensus verdict hours—and often days—before it settles on-chain.

```
Dispute Initiated
       │
       ▼
[ UMA Discord Deliberation ] ──> (Consensus forms at T + 6h) ───┐ Leading Signal
       │                                                         │
[ Polymarket Orderbook ]     ──> (Lagged trading at T + 24h) ───┤ Δ Arbitrage Spread
       │                                                         │
[ On-Chain Reveal & Settle ] ──> (Deterministic at T + 48h) ─────┘
```

---

## 2. The Quantitative Signal & Mathematical Framework

### 2.1 The Noise Problem
Raw Discord comment counts cannot be used as an trading signal. Retail chat is dominated by bagholders, spam, and non-tokenholding speculators. A simple unweighted vote poll yields negative alpha.

### 2.2 Empirical Bayes Voter Scoring ($S_u$)
To isolate signal from noise, every participant $u$ is scored via an **Empirical Bayes smoothing prior**:

$$S_u = \frac{R_u + N \cdot P}{G_u + N}$$

Where:
* $R_u$: Number of historically **correct** market dispute predictions made by user $u$.
* $G_u$: Total number of **gradeable** market dispute predictions made by user $u$ (decisive resolutions only; ambiguous splits excluded from penalty).
* $P = 0.50$: The uninformative prior accuracy (coin-flip baseline for uncalibrated newcomers).
* $N = 20$: The **Trust Parameter** (sample size threshold required to pull a voter away from the prior).

A user with 2 correct votes out of 2 is smoothed to:
$$\frac{2 + 20(0.50)}{2 + 20} = \frac{12}{22} \approx 54.5\%$$
Whereas an institutional analyst with 45 correct votes out of 50 achieves:
$$\frac{45 + 20(0.50)}{50 + 20} = \frac{55}{70} \approx 78.6\%$$

### 2.3 Exponential Power Weighting ($W_u$)
To amplify elite forecasters and heavily suppress uncalibrated participants, voting power scales quadratically:

$$W_u = (S_u)^p \quad (\text{with } p = 2.0)$$

* A $78.6\%$ calibrated voter receives weight: $0.786^2 = 0.618$.
* A $45.0\%$ uncalibrated voter receives weight: $0.450^2 = 0.203$.
* **The calibrated forecaster commands over 3.0× the voting influence of the noise trader.**

### 2.4 Point-in-Time Terminal Payoff Mapping
Under the Polymarket Conditional Tokens Framework (CTF), dispute stances map to discrete terminal values:

| Stance | Protocol Meaning | Terminal Payoff $V(u)$ |
|:---|:---|:---|
| **P1** | Outcome `NO` | **$0.00** |
| **P2** | Outcome `YES` | **$1.00** |
| **P3** | `50-50` Indeterminate | **$0.50** |
| **P4** | `Too Early` (Premature Proposal Rejection) | **$P_{\text{market}}(t_{\text{vote}})$** |

#### The "P4 Too Early" Payoff Innovation:
A `P4` vote does not resolve the market to binary zero or one; it rejects the immediate settlement and returns the contract to open trading. Hardcoding P4 to $0.50$ would introduce catastrophic artificial distortion. Polydispute anchors P4 to the **point-in-time observed trading price** $P_{\text{market}}(t_{\text{vote}})$, correctly capturing status-quo reversion.

### 2.5 Implied Settlement Expected Value & Arbitrage Spread
At any continuous timestamp $t$ across all active voters:

$$E[V(t)] = \frac{\sum_{u} W_u \cdot V_u(t)}{\sum_{u} W_u}$$

$$\Delta(t) = E[V(t)] - P_{\text{market}}(t)$$

When $|\Delta(t)| > \text{Execution Cost} + \text{Capital Hurdle}$, a structural mispricing exists.

---

## 3. Empirical Results: The 73.5% Accuracy Threshold

Backtesting across historical UMA dispute rounds yields:
* **Total Tracked Forecasters**: 781 unique participants.
* **Qualified Forecaster Pool**: 235 users ($\ge 10$ graded predictions, $\ge 50\%$ Bayesian accuracy).
* **Consensus Accuracy**: **73.5%** (25 out of 34 contested markets correctly predicted by weighted consensus prior to on-chain settlement).

---

## 4. Architecture & Engineering Stack

```
┌────────────────────────────────────────────────────────────────────────┐
│                        DATA INGESTION PIPELINE                         │
│  Discord Gateway (WSS) + Polymarket CLOB (REST) + UMA Subgraph         │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │ Raw JSON Batches
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      MOTHERDUCK CLOUD WAREHOUSE                        │
│  DuckDB Cloud OLAP Storage (clean_pm_markets, user_latest_stance)      │
│  Continuous Materialized Views (vw_dc_user_profiles)                   │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │ High-Speed In-Process Query
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                         FASTAPI BACKEND API                            │
│  Multi-tier In-Memory TTL Cache (60s Screener, 30s Live Detail)        │
│  Bayesian Vector Analytics Engine + Tenacity Auto-Reconnection         │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │ JSON (Pydantic v2 Contracts)
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                          REACT 18 FRONTEND                             │
│  Tailwind CSS + Recharts Linear Consensus Trajectories                │
│  Live Screener, Dispute Analytics, Voter Calibration Leaderboard       │
└────────────────────────────────────────────────────────────────────────┘
```

### Zero-Mock Policy
The platform implements a strict **Zero-Mock Policy**:
* If MotherDuck or the pipeline becomes unreachable, the client displays an explicit system telemetry diagnostic card.
* No synthetic fallback data is ever presented as real trading signals.
* The frontend navbar features a real-time roundtrip ping latency indicator and MotherDuck database connection monitor.

---

## 5. Deployment & Production Operations

The production deployment runs as a single, self-contained multi-stage Docker container on a **Hetzner Cloud VPS**:
* **Stage 1 (Node.js 20)**: Compiles React 18 Vite SPA assets into `/build/dist`.
* **Stage 2 (Python 3.12-slim + `uv`)**: Installs locked Python dependencies, copies `/build/dist`, and runs Uvicorn on port 8000.
* **Reverse Proxy**: Caddy provides zero-maintenance automatic TLS renewal and compression.

---

## 6. Key Takeaways

1. **Decentralized Oracles Have Informational Lead Times**: On-chain consensus is slow by design; off-chain consensus forms hours in advance.
2. **Bayesian Calibration Converts Noise into Signal**: Unweighted crowds are chaotic; Empirical Bayes power-weighted crowds are predictive ($73.5\%$ accuracy).
3. **Point-in-Time Payoff Modeling Prevents False Signals**: Dynamic status-quo handling (P4 anchoring) eliminates phantom arbitrage traps.
4. **DuckDB + MotherDuck Revolutionizes Financial ELT**: Replacing PostgreSQL with serverless DuckDB reduced query latency from $850\text{ ms}$ to $<35\text{ ms}$ without dedicated warehouse infrastructure costs.
