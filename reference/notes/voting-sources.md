# Voting Data Sources — Complete Map

What each source provides, what's duplicative, and the minimal set needed to compute τ.

---

## Source 1: VotingV2 Subgraph (Goldsky)

**Endpoint:** `https://api.goldsky.com/api/public/project_clus2fndawbcc01w31192938i/subgraphs/mainnet-voting-v2/0.1.1/gn`  
**Auth:** None  
**Format:** GraphQL  
**Existing code:** `experiments/dvm_votes.py`

### What it gives you

| Field | Location | Example |
|---|---|---|
| Dispute identifier | `priceRequests[].identifier.id` | `YES_OR_NO_QUERY` |
| Request timestamp | `priceRequests[].time` | `1722685917` |
| Ancillary data (hex) | `priceRequests[].ancillaryData` | `0x713a207469...` |
| Resolved price | `priceRequests[].price` | `0` (No), `1e18` (Yes), `-int256.min` (Early) |
| Round ID | `priceRequests[].rounds[].roundId` | `9970` |
| Total votes revealed | `rounds[].totalVotesRevealed` | `14519900.76...` (in UMA, 18 decimals) |
| Total committed | `rounds[].totalTokensCommitted` | `14524623.34...` |
| Cumulative stake | `rounds[].cumulativeStakeAtRound` | `18060369.15...` |
| Participation % | `rounds[].tokenVoteParticipationPercentage` | `80.39` |
| Vote groups | `rounds[].groups[]` | `{price, totalVoteAmount, votersAmount, won}` |
| Winner group | `rounds[].winnerGroup` | Same schema as group |
| **Committed votes** | `committedVotes[].voter.address` | `0x003a3b...` (= delegator address) |
| **Committed tokens** | `committedVotes[].numTokens` | `88768243172645643852996` (wei) |
| **Voter stats** | `committedVotes[].voter.*` | `voterStake`, `countReveals`, `countCorrectVotes`, etc. |
| **Revealed votes** | `revealedVotes[].voter.address` | `0x003a3b...` (= delegator address) |
| **Revealed price** | `revealedVotes[].price` | The actual vote cast |
| **Revealed tokens** | `revealedVotes[].numTokens` | Voting weight for this voter |
| **Revealed group** | `revealedVotes[].group.won` | Whether this voter was correct |
| Slashing data | `slashingTracker.*` | `wrongVoteSlashPerToken`, `totalSlashed` |

### Unique to this source
- **Per-voter voting weight** (`numTokens`) — nowhere else
- **Per-voter vote outcome** (`revealedVotes[].price`) — the actual on-chain vote
- **Aggregate tallies** — total participation, winner, slashing
- **Historical voter stats** — cumulative correct/wrong/no-vote counts
- **Round-level metadata** — participation requirements, slashing library

### Key constraint
- `voter.address` in committed/revealed votes = **delegator** address (the staker), NOT the delegate
- `committedVotes` are hashed (commit-reveal scheme) — no price until reveal phase
- `revealedVotes` contain the actual `price` (outcome)

---

## Source 2: UMA Rocks — `getPoolAnswers` API

**Endpoint:** `https://www.uma.rocks/api/getPoolAnswers`  
**Auth:** None  
**Format:** JSON array  
**Size:** ~1MB, hundreds of records

### What it gives you

| Field | Example |
|---|---|
| `ancillaryData` | `0x616e63696c6c617279...` (hex, contains `ancillaryDataHash`, `childBlockNumber`, etc.) |
| `question` | `"Will Trump post \"POTUS\" this week on Truth Social?"` |
| `answer` | `P1` (No), `P2` (Yes), `P3` (Unknown), `P4` (Early/too-early), `"Yes"` (governance) |
| `roundId` | `10135` |
| `timestamp` | `0` (pre-commitment) or unix timestamp |

### Unique to this source
- **Human-readable question text** for every dispute — the subgraph only has hex ancillaryData
- **Pre-commitment signal** — pool's intended vote BEFORE on-chain commit (when `timestamp: 0`)
- **Curated answer** — committee's deliberated P1-P4 decision

### Duplicative with subgraph
- `ancillaryData` — same hex blob, can join
- `roundId` — same as subgraph `rounds[].roundId`
- `answer` → can be derived from subgraph `revealedVotes[].price` after reveal (P1=0, P2=1e18, P3=5e17, P4=-int256.min)

### Key value
This is a **leading indicator** — available before the on-chain reveal. The subgraph only shows votes after reveal phase ends.

---

## Source 3: UMA Rocks — `getDelegates` API

**Endpoint:** `https://www.uma.rocks/api/getDelegates`  
**Auth:** None  
**Format:** JSON array of hex addresses

### What it gives you

```
["0x850BF360D7062257203854cEFc9A1629106d7a61", "0xeeD671a75689E7aFda9F658c8482B0939bEE2d34", ...]
```

~130 delegate (hot wallet) addresses controlled by UMA Rocks.

### Unique to this source
- **Identity key** — these addresses link to delegators via `DelegatorSet` events
- No other source tells you which addresses belong to UMA Rocks

### Not useful alone
These addresses do NOT appear in the subgraph's vote records. They're intermediate — you need them to look up delegators.

---

## Source 4: `DelegatorSet` Events (on-chain / Dune)

**Source:** `umaproject_ethereum.VotingV2_evt_DelegatorSet`  
**Access:** Dune Analytics, or direct Etherscan/RPC event scraping  
**Existing code:** None (only in Dune SQL)

### What it gives you

| Field | Description |
|---|---|
| `delegate` | The hot wallet address |
| `delegator` | The staker address (appears in subgraph as `voter.address`) |
| `evt_block_time` | When delegation was set |

### Unique to this source
- **Delegate → Delegator mapping** — the bridge between getDelegates API and subgraph voter addresses
- Historical delegation changes (a delegator can change delegates)

### Combined with getDelegates
```
getDelegates → 130 delegate addresses
    ↓ join on delegate
DelegatorSet → N delegator addresses  
    ↓ these appear as...
Subgraph revealedVotes[].voter.address
```

---

## Source 5: UMA Rocks — GitHub `answers/` directory

**Endpoint:** `https://api.github.com/repos/UMA-rocks/voting-committees/contents/answers`  
**Auth:** None (rate-limited)  
**Format:** JSON files per round

### What it gives you

Same data as `getPoolAnswers` API, but:
- Organized by round ID (directory per round)
- Only committee 1's answers (file `1.json`)
- Slower to poll (one request per round directory + one per file)

### ⚠️ FULLY DUPLICATIVE with `getPoolAnswers` API
The API returns the same data more efficiently. The GitHub source adds:
- PR history (deliberation trail before merge)
- Git blame (which committee member committed the answer)

**Verdict:** Skip for data pipeline. Only useful for auditing committee behavior.

---

## Source 6: UMA Rocks — Committee Metadata

**Endpoint:** `https://raw.githubusercontent.com/UMA-rocks/voting-committees/main/committees/1/metadata.json`  
**Auth:** None

### What it gives you

| Field | Example |
|---|---|
| `name` | `"UMA.rocks first voting committee"` |
| `multisig` | `3` (3/5 approval threshold) |
| `members[].github_id` | `jessioc`, `okayway1`, `scoutpol`, `cruzpoly`, `lancelot-c` |
| `members[].ethereum_address` | All redacted (`"0x"`) |

### Unique to this source
- Committee membership and governance rules
- GitHub IDs (linkable to Discord via user-provided mapping)

### Known Discord mapping

| GitHub | Discord |
|---|---|
| `jessioc` | `jessicaonlychild` |
| `okayway1` | `okayway1` |
| `scoutpol` | `poly.scout` |
| `cruzpoly` | `exquisite_wolf_79651` |
| `lancelot-c` | `frigodor` |

---

## Source 7: Etherscan / Direct RPC

**Source:** VotingV2 contract `VoteRevealed` events  
**Existing code:** `experiments/eth_scan.py`

### What it gives you
- Same `voter`, `price`, `numTokens` as subgraph revealedVotes
- Transaction-level detail (gas, block, tx hash)
- Filtering by `identifier` + `ancillaryData`

### ⚠️ FULLY DUPLICATIVE with VotingV2 Subgraph
The subgraph is strictly superior: paginated, indexed, includes aggregates, no rate limits.

**Verdict:** Fallback only. Use subgraph.

---

## Source 8: Discord — Committee Member Watch (5 handles)

**Existing code:** `experiments/eda_discord.py`  
**Data:** ~11K messages from UMA `#disputes` and UMA Rocks channels

### Reframed value proposition

UMA Rocks is correct 99.5% of the time. Broad Discord sentiment from independent voters adds ~zero marginal information — they converge to the same answer due to slashing incentives.

**Discord is only valuable as a LEADING INDICATOR for the 5 committee members**, whose comments appear BEFORE the `getPoolAnswers` API updates:

| Discord handle | Watch for |
|---|---|
| `jessicaonlychild` | Stance on active disputes |
| `okayway1` | Stance on active disputes |
| `poly.scout` | Stance on active disputes |
| `exquisite_wolf_79651` | Stance on active disputes |
| `frigodor` | Stance on active disputes (lancelot-c, UMA Rocks founder) |

### What makes this a leading indicator
The committee deliberates in Discord BEFORE formalizing their vote in the GitHub PR. If 3/5 members express a clear P1/P2 stance in Discord, the committee vote is effectively decided — you just saw it hours before `getPoolAnswers` updates.

### NOT worth building for
- Broad independent voter sentiment (the other ~78% of weight)
- LLM-based stance classification of general messages
- Identity resolution for non-committee addresses

---

## Source 9: Polymarket (Gamma API)

**Existing code:** `pmxt` library, SQLite storage  
**Data:** Market prices, conditions, outcomes

### What it gives you
- Current market price (retail sentiment)
- Market metadata (question, description, resolution source)
- Condition IDs linkable to UMA disputes via `ancillaryData`

### Unique to this source
- **Polymarket price** — the other side of the divergence calculation

---

## Sources You Don't Need

| Source | Why drop it |
|---|---|
| **GitHub `answers/`** | Fully duplicated by `getPoolAnswers` API |
| **Etherscan RPC** | Fully duplicated by subgraph |
| **`getDelegates` API** | Not needed if you treat UMA Rocks as a ~22% bloc with known vote direction |
| **`DelegatorSet` events** | Same — per-address resolution is unnecessary |
| **`getUmaPrice` API** | USD display only, not for signal |
| **VotingV2 Subgraph** (for production) | Backtesting/validation only — not needed for live signal |
| **Broad Discord** | Independent voters converge to same answer; noise > signal |

---

## Minimal Production Sources

| Source | Purpose | Priority |
|---|---|---|
| **`getPoolAnswers` API** | UMA Rocks' vote direction → τ ≈ 0.995 × direction | 🔴 Core |
| **Polymarket API** | Market price → divergence detection | 🔴 Core |
| **Discord (5 handles only)** | Leading indicator BEFORE getPoolAnswers updates | 🟡 Edge enhancement |
| **VotingV2 Subgraph** | Backtesting, weight validation, edge case analysis | 🔵 Offline only |

---

## Signal Timing Model

The edge decays as information becomes public. The timeline for a dispute:

```
T0  Dispute created on Polygon → bridges to Ethereum
│   Polymarket price exists. Market may be mispriced.
│
│   ══════════════════════════════════════════════════
│   EDGE WINDOW 1: Discord (hours of lead time)
│   ══════════════════════════════════════════════════
│
T1  Committee members discuss in Discord (#disputes / UMA Rocks)
│   → If 3/5 express clear P1/P2 stance, outcome is ~decided
│   → You can infer pool's vote BEFORE it's formalized
│   
│   ══════════════════════════════════════════════════
│   EDGE WINDOW 2: getPoolAnswers (minutes to hours)
│   ══════════════════════════════════════════════════
│
T2  GitHub PR created/updated with committee answers
│   
T3  PR merged to main (by 11:00 UTC)
│   getPoolAnswers API updates → structured P1/P2/P3/P4
│   → τ ≈ 0.995 in direction of answer
│   → Compare to Polymarket price → detect divergence
│
│   ══════════════════════════════════════════════════
│   EDGE DECAYS: public information
│   ══════════════════════════════════════════════════
│
T4  On-chain commit at 12:00 UTC (vote is hashed, not readable)
│
T5  Reveal phase → everyone can see all votes
│   → Edge is gone. Market should have adjusted.
│
T6  Resolution → dispute settled on-chain
```

### Edge window analysis

| Window | Trigger | Duration | Signal quality | Engineering cost |
|---|---|---|---|---|
| **Discord → getPoolAnswers** | Committee member comment | Hours (possibly 6-24h) | Medium (requires NLP/manual interpretation, 3/5 threshold) | Medium (monitor 5 handles, classify stance) |
| **getPoolAnswers → on-chain commit** | API update | ~1 hour (11:00-12:00 UTC) | High (structured P1/P2, 99.5% accuracy) | Low (poll one API endpoint) |
| **Post-commit** | On-chain event | 0 | Edge gone | — |

---

## Proposed System Design

### Architecture: Two-tier signal pipeline

```
┌─────────────────────────────────────────────────────┐
│                    TIER 1: CORE                     │
│           (2 API calls, runs every 5 min)           │
│                                                     │
│  ┌──────────────┐       ┌──────────────────┐       │
│  │ getPoolAnswers│──────▶│ Dispute Matcher  │       │
│  │ (poll)        │       │                  │       │
│  └──────────────┘       │ Match ancillary  │       │
│                          │ data / question  │       │
│  ┌──────────────┐       │ to Polymarket    │       │
│  │ Polymarket   │──────▶│ market price     │       │
│  │ API (poll)   │       │                  │       │
│  └──────────────┘       └────────┬─────────┘       │
│                                  │                  │
│                          ┌───────▼────────┐        │
│                          │ Divergence     │        │
│                          │ Calculator     │        │
│                          │                │        │
│                          │ gap = 0.995    │        │
│                          │   - mkt_price  │        │
│                          │                │        │
│                          │ if gap > θ:    │        │
│                          │   → ALERT      │        │
│                          └───────┬────────┘        │
│                                  │                  │
│                          ┌───────▼────────┐        │
│                          │ Alert Output   │        │
│                          │ (Telegram/log) │        │
│                          └────────────────┘        │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                 TIER 2: EARLY SIGNAL                │
│          (Discord WebSocket / poll, 5 handles)      │
│                                                     │
│  ┌──────────────┐       ┌──────────────────┐       │
│  │ Discord      │──────▶│ Committee Stance │       │
│  │ #disputes    │       │ Classifier       │       │
│  │ + UMA Rocks  │       │                  │       │
│  │ channels     │       │ Filter to 5      │       │
│  └──────────────┘       │ handles only     │       │
│                          │                  │       │
│                          │ Extract P1/P2   │       │
│                          │ stance per       │       │
│                          │ dispute          │       │
│                          │                  │       │
│                          │ If 3/5 agree:   │       │
│                          │ → EARLY ALERT   │       │
│                          └────────┬─────────┘       │
│                                   │                 │
│                          ┌────────▼────────┐       │
│                          │ Cross-ref with  │       │
│                          │ Polymarket      │       │
│                          │ price → early   │       │
│                          │ divergence      │       │
│                          └─────────────────┘       │
└─────────────────────────────────────────────────────┘
```

### Tier 1: Core divergence detection

**What:** Poll `getPoolAnswers` + Polymarket API every 5 minutes. When a new answer appears (or changes from P4 to P1/P2), compare against market price. Alert if gap exceeds threshold θ.

**Complexity:** Trivial. Two HTTP calls, a string match, and a comparison.

**Key engineering tasks:**
1. Dispute matching — join `getPoolAnswers.ancillaryData` to Polymarket market. The `question` field in getPoolAnswers makes fuzzy matching possible even without solving the hex ancillaryData join.
2. Threshold tuning — what gap size (θ) is worth acting on? Need backtesting.
3. P4 handling — P4 (too early to resolve) is the most common answer for new disputes. The signal fires when P4 changes to P1/P2.

**Latency:** ~1 hour before on-chain commit (getPoolAnswers updates after PR merge at ~11:00 UTC, commit at 12:00 UTC).

### Tier 2: Discord early signal

**What:** Monitor Discord for messages from the 5 committee handles. When they discuss an active dispute, classify their stance. If 3/5 lean one way → early signal.

**Complexity:** Medium. Need to:
1. Associate a Discord message with a specific active dispute (match by question text / keywords)
2. Classify stance (simple P1/P2 mention, or LLM classification for nuanced discussion)
3. Track 3/5 quorum

**Latency:** Hours to a day before getPoolAnswers updates.

**When to build:** After Tier 1 is validated. Only worth the engineering if Tier 1 backtesting shows the gap persists long enough for the extra lead time to matter.

### What NOT to build

- Per-voter weight resolution (getDelegates → DelegatorSet → subgraph)
- Broad Discord NLP for non-committee members
- Real-time subgraph WebSocket feed
- LLM classification of general UMA community discussion

---

## Open Questions for Backtesting

1. **How long does the gap persist?** After getPoolAnswers updates with a P1/P2 answer, how quickly does Polymarket adjust? If the gap closes in minutes, Tier 2 is necessary. If it persists for hours, Tier 1 alone is sufficient.

2. **How often do disputes have meaningful gaps?** If UMA Rocks votes P2 (Yes) and Polymarket is at 95%, there's no edge. What's the distribution of gap sizes?

3. **P4 → P1/P2 transition timing.** How long do disputes stay at P4 before the committee decides? This determines the window between dispute creation and actionable signal.

4. **How often do committee members telegraph their vote in Discord?** If they rarely discuss before voting, Tier 2 adds no value.

---

## Join Keys (simplified)

For the production pipeline, the critical join is:

```
getPoolAnswers.question  ←──fuzzy match──→  Polymarket market title
getPoolAnswers.ancillaryData  ←──hex join──→  UmaCtfAdapter ancillaryData (Polygon)
```

The `ancillaryData` in getPoolAnswers contains `ancillaryDataHash` + `childBlockNumber` + `childOracle` + `childRequester` + `childChainId`. The `ancillaryDataHash` can be matched to the Polymarket CTF adapter's original ancillaryData on Polygon.

### Cross-chain hashing trap (reminder)
When ancillaryData bridges from Polygon to Ethereum, it gets keccak256-hashed. The subgraph field will contain `ancillaryDataHash:` prefix. Match via `identifier` + `time` as fallback, or pre-compute the hash.
