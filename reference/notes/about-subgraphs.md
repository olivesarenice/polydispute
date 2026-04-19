# UMA Subgraph Monorepo — Beginner Guide

## What Is a Subgraph?

A **subgraph** is an indexer for blockchain data. Blockchains are append-only event logs — querying them directly is slow and expensive. A subgraph:

1. **Watches** specific smart contracts on a blockchain
2. **Listens** for specific events those contracts emit (e.g., `VoteCommitted`, `PriceResolved`)
3. **Transforms** those raw events into structured, queryable entities
4. **Exposes** a GraphQL API you can query instantly

Think of it as: **ETL pipeline for blockchain → GraphQL database**.

The dominant hosting platforms are [The Graph](https://thegraph.com/) and [Goldsky](https://goldsky.com/).

---

## Architecture of a Single Subgraph Package

Every subgraph package follows this structure:

```
packages/<name>/
├── schema.graphql          # 1. DATA MODEL — defines queryable entities (like a DB schema)
├── manifest/
│   ├── templates/
│   │   └── subgraph.template.yaml   # 2. MANIFEST TEMPLATE — mustache template
│   └── data/
│       ├── mainnet.json    # 3. NETWORK CONFIG — contract addresses per chain
│       └── polygon.json
├── subgraph.yaml           # 4. GENERATED MANIFEST — output of (template + config)
├── abis/                   # 5. CONTRACT ABIs — JSON interfaces of the smart contracts
├── src/
│   └── index.ts            # 6. MAPPINGS — AssemblyScript handlers that transform events → entities
├── scripts/
│   ├── build-manifest.sh   # Runs mustache to generate subgraph.yaml
│   └── deploy.sh           # Deployment script
└── package.json
```

### The Build Pipeline

```
manifest/data/polygon.json  ─┐
                              ├─ mustache ──► subgraph.yaml ──► graph codegen ──► graph build
manifest/templates/*.yaml   ─┘                                   (generates      (compiles to
                                                                  TS types)       WASM)
```

1. **`mustache`** templates the `subgraph.yaml` manifest by injecting network-specific contract addresses and start blocks
2. **`graph codegen`** reads the manifest + ABIs + schema, generates TypeScript types for your entities and events
3. **`graph build`** compiles the AssemblyScript mappings into WASM bytecode that the indexer node executes

---

## The Four Key Files (in learning order)

### 1. `schema.graphql` — What data do you want to query?

Defines your GraphQL entities. Each entity maps to a "table" in the indexed database.

```graphql
type PriceRequest @entity {
  id: ID!
  identifier: PriceIdentifier!
  time: BigInt!
  roundId: BigInt!
  isResolved: Boolean!
  price: BigInt
}
```

### 2. `manifest/data/<network>.json` — Where are the contracts?

Network-specific configuration: contract addresses and the block number to start indexing from.

```json
{
  "network": "mainnet",
  "identifierWhitelistAddress": "0xcf649d9da4d1362c4daea67573430bd6f945e570",
  "identifierWhitelistStartBlock": 9937679
}
```

### 3. `subgraph.yaml` (generated) — What to index?

The manifest tells the indexer:
- Which blockchain network
- Which contract address + ABI
- Which events to listen for
- Which handler function to call for each event

### 4. `src/index.ts` — How to transform events into entities?

AssemblyScript (a TypeScript subset that compiles to WASM) handler functions. Each handler receives a typed event object and writes entities to the store.

```typescript
export function handleVoteCommitted(event: VoteCommitted): void {
  let entity = new CommittedVote(event.transaction.hash.toHex())
  entity.voter = event.params.voter
  entity.roundId = event.params.roundId
  entity.save()
}
```

---

## Monorepo Structure

```
reference/subgraphs/
├── package.json            # Root — Yarn workspaces + Lerna config
├── lerna.json              # Lerna monorepo orchestration
├── scripts/
│   └── deploy.sh           # Shared deployment script (TheGraph / Goldsky / Docker)
└── packages/
    ├── voting/             # UMA Voting V1 oracle events
    ├── votingV2/           # UMA Voting V2 oracle events
    ├── optimistic-oracle/  # Optimistic Oracle V1
    ├── optimistic-oracle-v2/  # Optimistic Oracle V2 (+ call handlers)
    ├── optimistic-oracle-v3/  # Optimistic Oracle V3
    ├── managed-oracle-v2/  # Managed OO V2 (reuses OO V2 code)
    ├── skinny-optimistic-oracle/  # Skinny OO variant
    ├── optimistic-governor/ # Optimistic Governor (DAO governance)
    ├── financial-contracts/ # ExpiringMultiParty + Perpetual contracts
    ├── long-short-pair/    # LSP token contracts
    └── token/              # UMA voting token (ERC20) events
```

### What each package indexes

| Package | What it watches | Why it matters |
|---------|----------------|----------------|
| `voting` | V1 oracle: vote commits, reveals, price requests, rewards | Core dispute resolution mechanism |
| `votingV2` | V2 oracle: same events, upgraded contract | Current production oracle |
| `optimistic-oracle` | OO V1: price requests, proposals, disputes | "Optimistic" truth — propose answer, challenge if wrong |
| `optimistic-oracle-v2` | OO V2: + bond/liveness settings, call handlers | Enhanced oracle with configurable parameters |
| `optimistic-oracle-v3` | OO V3: assertions, disputes, settlements | Latest oracle — assertion-based model |
| `managed-oracle-v2` | Managed OO V2: custom bond/liveness per requester | Wrapper around OO V2 for managed deployments |
| `skinny-optimistic-oracle` | Skinny OO: minimal oracle variant | Gas-optimized oracle |
| `optimistic-governor` | DAO governance proposals via OO | Snapshot → on-chain execution |
| `financial-contracts` | EMP + Perpetual: positions, liquidations, disputes | DeFi derivative contracts |
| `long-short-pair` | LSP: token creation, settlements | Binary outcome tokens |
| `token` | UMA token: transfers, approvals | Token analytics |

### Root-level tooling

- **Lerna** (`lerna.json`): Orchestrates commands across all packages (`yarn test`, `yarn build`)
- **Yarn Workspaces** (`package.json`): Shared dependency resolution. `yarn install` at root installs deps for all packages
- **`scripts/deploy.sh`**: Shared deploy script that routes to TheGraph hosted/studio, Goldsky, or Docker based on env vars

---

## Learning Path

### Phase 1: Read (no code changes)
1. Read `packages/voting/schema.graphql` — understand the entity model
2. Read `packages/voting/manifest/data/mainnet.json` — see the contract addresses
3. Read `packages/voting/manifest/templates/subgraph.template.yaml` — see event → handler mapping
4. Read `packages/voting/src/index.ts` — trace one handler end-to-end (e.g., `handleVoteCommitted`)

### Phase 2: Query
1. Pick a deployed subgraph URL from the README (e.g., the Goldsky OO V3 endpoint)
2. Open the GraphQL playground and run queries against it
3. Understand what data is available and how entities relate

### Phase 3: Modify
1. Add a new field to an existing entity in `schema.graphql`
2. Populate it in the mapping handler in `src/index.ts`
3. Run `yarn codegen && yarn build` to verify it compiles

### Phase 4: Deploy
1. Use Goldsky (you're already authenticated): `goldsky subgraph deploy <name>/<version> --path .`
2. Query your deployed subgraph

---

## Key Gotchas

> [!WARNING]
> **AssemblyScript ≠ TypeScript.** Mappings look like TS but compile to WASM. No `async/await`, no closures, limited stdlib. Many things that work in TS will silently fail or crash.

> [!WARNING]
> **`startBlock` matters.** If set too low, indexing takes forever. If set too high, you miss events. Always set it to the contract deployment block.

> [!IMPORTANT]
> **Polygon `voting` data is nearly empty.** The `polygon.json` config has empty arrays for `VotingDataSources`, `VotingAncillaryDataSources`, and `StoreDataSources`. The only contracts indexed on Polygon for this package are `IdentifierWhitelist`, `AddressWhitelist`, and `Registry`. For full voting data, use `mainnet`.

> [!NOTE]
> **`apiVersion` in manifests must match `graph-cli` version.** The installed `graph-cli ^0.67.3` requires `apiVersion: 0.0.5` minimum. The templates originally had `0.0.4` (fixed in this session).
