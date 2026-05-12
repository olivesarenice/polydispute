"""
Query UMA DVM vote breakdowns from the VotingV2 subgraph (Goldsky).

Paginates through ALL priceRequests (like vote.uma.xyz does), then filters
locally for the (identifier, time) pairs you care about from MOOv2.

Usage:
    uv run experiments/dvm_votes.py
    uv run experiments/dvm_votes.py path/to/moov2_requests.json
"""

import json
import sys
from decimal import Decimal

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VOTING_V2_SUBGRAPH = (
    "https://api.goldsky.com/api/public/"
    "project_clus2fndawbcc01w31192938i/"
    "subgraphs/mainnet-voting-v2/0.1.1/gn"
)

PAGE_SIZE = 200

# Standard UMA vote prices (18 decimals)
VOTE_LABELS = {
    0: "No",
    10**18: "Yes",
    5 * 10**17: "Unknown / 50-50",
}

# ---------------------------------------------------------------------------
# GraphQL queries (ported from voter-dapp-v2)
# ---------------------------------------------------------------------------

# Lightweight paginated query — matches what vote.uma.xyz fires
PAST_VOTES_LIGHT_QUERY = """
query getPastVotesLight($skip: Int!, $limit: Int!) {
  priceRequests(
    first: $limit
    skip: $skip
    where: { isResolved: true }
    orderBy: resolvedPriceRequestIndex
    orderDirection: desc
  ) {
    identifier { id }
    price
    time
    ancillaryData
    resolvedPriceRequestIndex
    isGovernance
    rollCount
  }
}
"""

# Full detail query — vote breakdown for a single vote by its index
VOTE_DETAIL_QUERY = """
query getVoteDetails($index: Int!, $latestRoundLimit: Int!) {
  priceRequests(where: { resolvedPriceRequestIndex: $index }) {
    identifier { id }
    price
    time
    ancillaryData
    resolvedPriceRequestIndex
    isResolved
    isGovernance
    rollCount
    latestRound {
      totalVotesRevealed
      totalTokensCommitted
      minAgreementRequirement
      minParticipationRequirement
      roundId
      groups(first: $latestRoundLimit) {
        price
        totalVoteAmount
        won
      }
      committedVotes(first: $latestRoundLimit) { id }
      revealedVotes(first: $latestRoundLimit) {
        id
        voter { address }
        price
        numTokens
      }
    }
  }
}
"""

# Active (unresolved) votes with live tallies
ACTIVE_VOTES_QUERY = """
{
  priceRequests(
    where: { isResolved: false }
    orderBy: resolvedPriceRequestIndex
    orderDirection: desc
  ) {
    identifier { id }
    price
    time
    ancillaryData
    resolvedPriceRequestIndex
    isResolved
    isGovernance
    rollCount
    latestRound {
      totalVotesRevealed
      minAgreementRequirement
      minParticipationRequirement
      totalTokensCommitted
      groups {
        price
        totalVoteAmount
        won
      }
      committedVotes(first: 1000) { id }
      revealedVotes(first: 1000) {
        id
        voter { address }
        price
        numTokens
      }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Subgraph client
# ---------------------------------------------------------------------------


def query_subgraph(query: str, variables: dict | None = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = requests.post(
        VOTING_V2_SUBGRAPH,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"Subgraph errors: {json.dumps(data['errors'], indent=2)}")
    return data["data"]


def fetch_all_past_votes() -> list[dict]:
    """Paginate through all resolved priceRequests, exactly like vote.uma.xyz."""
    all_requests = []
    skip = 0
    while True:
        data = query_subgraph(
            PAST_VOTES_LIGHT_QUERY, {"skip": skip, "limit": PAGE_SIZE}
        )
        page = data.get("priceRequests", [])
        if not page:
            break
        all_requests.extend(page)
        print(f"  Fetched {len(all_requests)} resolved votes (page {skip // PAGE_SIZE + 1})...")
        if len(page) < PAGE_SIZE:
            break
        skip += PAGE_SIZE
    return all_requests


def fetch_active_votes() -> list[dict]:
    """Fetch all currently active (unresolved) votes."""
    data = query_subgraph(ACTIVE_VOTES_QUERY)
    return data.get("priceRequests", [])


def fetch_vote_detail(resolved_index: int) -> dict | None:
    """Fetch full vote breakdown by resolvedPriceRequestIndex."""
    data = query_subgraph(
        VOTE_DETAIL_QUERY,
        {"index": resolved_index, "latestRoundLimit": 1000},
    )
    results = data.get("priceRequests", [])
    return results[0] if results else None


# ---------------------------------------------------------------------------
# Matching & parsing
# ---------------------------------------------------------------------------


def identifier_text_to_hex(text: str) -> str:
    """Convert identifier text to bytes32 hex (right-padded with zeros)."""
    return "0x" + text.encode("utf-8").ljust(32, b"\x00").hex()


def parse_identifier(identifier_id: str) -> str:
    """Decode bytes32 identifier hex to utf-8 string."""
    try:
        return bytes.fromhex(identifier_id[2:]).rstrip(b"\x00").decode("utf-8")
    except Exception:
        return identifier_id


def label_vote(price_raw: int | str) -> str:
    p = int(price_raw)
    return VOTE_LABELS.get(p, f"Other ({p})")


def find_matching_votes(
    all_votes: list[dict],
    moov2_requests: list[dict],
) -> list[tuple[dict, dict | None]]:
    """
    Match MOOv2 (identifier, time) pairs against fetched priceRequests.

    Returns list of (moov2_request, matching_vote_or_None).
    """
    # Build lookup: (identifier_hex, time_str) -> vote
    vote_index: dict[tuple[str, str], dict] = {}
    for v in all_votes:
        key = (v["identifier"]["id"], v["time"])
        vote_index[key] = v

    results = []
    for req in moov2_requests:
        identifier_hex = identifier_text_to_hex(req["identifier"])
        time_str = str(req["time"])
        match = vote_index.get((identifier_hex, time_str))
        results.append((req, match))

    return results


def parse_vote_result(pr: dict) -> dict:
    """Parse a priceRequest entity into a structured result dict."""
    identifier = parse_identifier(pr["identifier"]["id"])
    latest_round = pr.get("latestRound") or {}

    # Participation
    committed_count = len(latest_round.get("committedVotes", []))
    revealed_count = len(latest_round.get("revealedVotes", []))
    total_revealed = Decimal(latest_round.get("totalVotesRevealed", "0"))
    total_committed = latest_round.get("totalTokensCommitted")
    total_committed = Decimal(total_committed) if total_committed else None

    participation = {
        "unique_commit_addresses": committed_count,
        "unique_reveal_addresses": revealed_count,
        "total_tokens_voted_with": total_revealed,
        "total_tokens_committed": total_committed,
        "min_agreement_requirement": latest_round.get("minAgreementRequirement"),
        "min_participation_requirement": latest_round.get("minParticipationRequirement"),
    }

    # Vote groups
    groups = []
    for g in latest_round.get("groups", []):
        raw_price = int(g["price"])
        amount = Decimal(g["totalVoteAmount"])
        groups.append({
            "vote": label_vote(raw_price),
            "vote_raw": raw_price,
            "tokens_voted_with": amount,
            "won": g.get("won", False),
            "pct": float(amount / total_revealed * 100) if total_revealed > 0 else 0,
        })

    # Per-address revealed votes
    revealed_by_address = {}
    for rv in latest_round.get("revealedVotes", []):
        addr = rv["voter"]["address"]
        revealed_by_address[addr] = {
            "vote": label_vote(rv["price"]),
            "vote_raw": int(rv["price"]),
            "num_tokens": int(rv.get("numTokens", 0)),
        }

    return {
        "identifier": identifier,
        "identifier_hex": pr["identifier"]["id"],
        "time": int(pr["time"]),
        "is_resolved": pr.get("isResolved", True),
        "resolved_price": pr.get("price"),
        "resolved_price_label": label_vote(pr["price"]) if pr.get("price") else None,
        "resolved_price_request_index": pr.get("resolvedPriceRequestIndex"),
        "is_governance": pr.get("isGovernance", False),
        "roll_count": int(pr.get("rollCount", 0)),
        "ancillary_data": pr.get("ancillaryData"),
        "participation": participation,
        "results": groups,
        "revealed_by_address": revealed_by_address,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def print_vote_result(result: dict, index: int = 0) -> None:
    print(f"\n{'=' * 60}")
    print(f"Vote {index + 1}: {result['identifier']}")
    print(f"{'=' * 60}")
    print(f"  Time:        {result['time']}")
    print(f"  Resolved:    {result['is_resolved']}")
    if result["is_resolved"] and result["resolved_price_label"]:
        print(f"  Result:      {result['resolved_price_label']}")
    print(f"  Governance:  {result['is_governance']}")
    print(f"  Roll Count:  {result['roll_count']}")
    print(f"  Index:       {result['resolved_price_request_index']}")

    p = result["participation"]
    print(f"\n  Participation:")
    print(f"    Commits:   {p['unique_commit_addresses']}")
    print(f"    Reveals:   {p['unique_reveal_addresses']}")
    print(f"    Tokens:    {p['total_tokens_voted_with']:,.2f}")
    if p["total_tokens_committed"]:
        print(f"    Committed: {p['total_tokens_committed']:,.2f}")

    if result["results"]:
        print(f"\n  Vote Breakdown:")
        for g in sorted(result["results"], key=lambda x: x["pct"], reverse=True):
            won = " ✓" if g["won"] else ""
            print(
                f"    {g['vote']:20s} | "
                f"{g['tokens_voted_with']:>15,.2f} tokens | "
                f"{g['pct']:6.2f}%{won}"
            )
    else:
        print("\n  (lightweight data — use --detail for full breakdown)")


def main():
    # Default MOOv2 test data
    moov2_data = [
        {"identifier": "YES_OR_NO_QUERY", "time": "1762982877"},
        {"identifier": "YES_OR_NO_QUERY", "time": "1770152454"},
    ]

    if len(sys.argv) > 1 and sys.argv[1] != "--detail":
        with open(sys.argv[1]) as f:
            data = json.load(f)
        moov2_data = data.get("data", data).get(
            "optimisticPriceRequests", data if isinstance(data, list) else []
        )

    fetch_detail = "--detail" in sys.argv

    print(f"Endpoint: {VOTING_V2_SUBGRAPH}")
    print(f"Looking up {len(moov2_data)} MOOv2 requests...\n")

    # Step 1: Fetch all resolved votes (paginated, like the website)
    print("Step 1: Fetching all resolved votes...")
    all_resolved = fetch_all_past_votes()
    print(f"  Total resolved votes: {len(all_resolved)}")

    # Step 2: Also fetch active (unresolved) votes
    print("\nStep 2: Fetching active votes...")
    all_active = fetch_active_votes()
    print(f"  Active votes: {len(all_active)}")

    all_votes = all_resolved + all_active

    # Step 3: Match MOOv2 requests
    print(f"\nStep 3: Matching {len(moov2_data)} MOOv2 requests...")
    matches = find_matching_votes(all_votes, moov2_data)

    found = 0
    for i, (req, match) in enumerate(matches):
        if match is None:
            print(f"\n{'=' * 60}")
            print(f"Vote {i + 1}: {req['identifier']} @ {req['time']}")
            print(f"{'=' * 60}")
            print("  NOT FOUND — request may not have been escalated to DVM vote")
        else:
            found += 1
            # If --detail, fetch the full breakdown using the resolvedPriceRequestIndex
            if fetch_detail and match.get("resolvedPriceRequestIndex") is not None:
                print(f"\n  Fetching full details for index {match['resolvedPriceRequestIndex']}...")
                detailed = fetch_vote_detail(int(match["resolvedPriceRequestIndex"]))
                if detailed:
                    match = detailed

            result = parse_vote_result(match)
            print_vote_result(result, i)

    print(f"\n{'=' * 60}")
    print(f"Summary: {found}/{len(moov2_data)} requests found in DVM")


if __name__ == "__main__":
    main()
