"""Mathematical engine for Polydispute Bayesian consensus calibration.

Implements:
- Empirical Bayes accuracy smoothing: S = (R + N*P) / (G + N)
- Power-law consensus weighting: W = S^p
- Time-series stepped trajectory generation
- Generalized power-mean cohort RMS accuracy
- Deterministic scatter jitter
"""

import hashlib
from typing import Any
import numpy as np
import pandas as pd


def compute_bayesian_score(
    correct: int,
    gradeable: int,
    trust_number: int = 20,
    prior_score: float = 0.50,
) -> float:
    """
    Empirical Bayes smoothed accuracy score (0.00 to 1.00).
    S = (correct + N * P) / (gradeable + N)
    """
    numerator = float(correct) + (float(trust_number) * float(prior_score))
    denominator = float(gradeable) + float(trust_number)
    if denominator <= 0:
        return prior_score
    return max(0.0, min(1.0, numerator / denominator))


def compute_power_weight(score: float, exponent: float = 2.0) -> float:
    """
    Applies power law to amplify high-accuracy voters relative to low-accuracy voters.
    W = S^p
    """
    return float(score**exponent)


def get_voter_jitter(author_username: str) -> float:
    """
    Deterministic horizontal scatter jitter in range [-0.16, +0.16]
    based on voter username hash.
    """
    h = int(hashlib.md5(author_username.encode("utf-8")).hexdigest()[:8], 16)
    return round(((h % 1000) / 500.0 - 1.0) * 0.16, 5)


def get_price_at_timestamp(
    ts: pd.Timestamp,
    price_df: pd.DataFrame,
    fallback_val: float = 0.50,
) -> float:
    """Point-in-time orderbook price lookup for P4 payoff anchoring."""
    if price_df is None or price_df.empty or "timestamp" not in price_df.columns:
        return fallback_val

    ts_comp = ts
    if ts.tzinfo is None and price_df["timestamp"].dt.tz is not None:
        ts_comp = ts.tz_localize("UTC")
    elif ts.tzinfo is not None and price_df["timestamp"].dt.tz is None:
        ts_comp = ts.tz_localize(None)

    sub = price_df[price_df["timestamp"] <= ts_comp]
    if not sub.empty:
        return float(sub.iloc[-1]["yes_price"])
    return float(price_df.iloc[0]["yes_price"])


def build_market_analytics(
    votes_df: pd.DataFrame,
    price_df: pd.DataFrame,
    user_profiles: dict[str, dict[str, Any]],
    trust_number: int = 20,
    prior_score: float = 0.50,
    power_exponent: float = 2.0,
    min_accuracy_filter: float = 0.0,
    fallback_price: float = 0.50,
) -> dict[str, Any]:
    """
    Computes consensus trajectory, voter distribution dot-map items,
    cohort RMS accuracy, and chat reasoning records.
    """
    vote_types = ["P1", "P2", "P3", "P4"]

    if votes_df.empty:
        return {
            "consensus_trajectory": [],
            "voter_distribution": [],
            "cohort_rms": {"P1": 0.50, "P2": 0.50, "P3": 0.50, "P4": 0.50},
            "cohort_counts": {"P1": 0, "P2": 0, "P3": 0, "P4": 0},
            "chat_messages": [],
            "implied_ev": fallback_price,
        }

    votes = votes_df.sort_values("timestamp").reset_index(drop=True).copy()

    # Precompute scores & weights for each vote row
    b_scores = []
    p_weights = []
    for _, row in votes.iterrows():
        uname = row["author_username"]
        profile = user_profiles.get(uname, {})
        corr = profile.get("correct_predictions", 0)
        grad = profile.get("gradeable_predictions", 0)
        score = compute_bayesian_score(corr, grad, trust_number, prior_score)
        b_scores.append(score)
        p_weights.append(compute_power_weight(score, power_exponent))

    votes["bayesian_score"] = b_scores
    votes["power_weight"] = p_weights

    # Apply voter accuracy exclusion filter if active
    if min_accuracy_filter > 0:
        threshold = min_accuracy_filter / 100.0
        votes = votes[votes["bayesian_score"] >= threshold].copy()

    if votes.empty:
        return {
            "consensus_trajectory": [],
            "voter_distribution": [],
            "cohort_rms": {"P1": 0.50, "P2": 0.50, "P3": 0.50, "P4": 0.50},
            "cohort_counts": {"P1": 0, "P2": 0, "P3": 0, "P4": 0},
            "chat_messages": [],
            "implied_ev": fallback_price,
        }

    # 1. Generate stepped consensus trajectory (Latest Stance per User)
    user_stances: dict[str, tuple[str, float, float]] = {}  # uname -> (vote_type, weight, payoff)
    trajectory_events = []

    for _, row in votes.iterrows():
        ts = row["timestamp"]
        vtype = row["vote_type"]
        uname = row["author_username"]
        weight = row["power_weight"]

        # Payoff assignment
        if vtype == "P1":
            payoff = 0.0
        elif vtype == "P2":
            payoff = 1.0
        elif vtype == "P3":
            payoff = 0.50
        elif vtype == "P4":
            payoff = get_price_at_timestamp(ts, price_df, fallback_val=fallback_price)
        else:
            payoff = 0.50

        user_stances[uname] = (vtype, weight, payoff)

        # Aggregate active stances
        v_weights = {vt: 0.0 for vt in vote_types}
        sum_w_payoff = 0.0
        for u_vtype, u_weight, u_payoff in user_stances.values():
            v_weights[u_vtype] += u_weight
            sum_w_payoff += (u_weight * u_payoff)

        total_weighted = sum(v_weights.values())
        implied_ev = (sum_w_payoff / total_weighted) if total_weighted > 0 else 0.50

        # Market price at timestamp
        m_price = get_price_at_timestamp(ts, price_df, fallback_val=fallback_price)

        trajectory_events.append({
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "author_username": uname,
            "vote_type": vtype,
            "yes_price": round(m_price, 4),
            "p1_weighted_pct": round((v_weights["P1"] / total_weighted * 100.0) if total_weighted > 0 else 0.0, 2),
            "p2_weighted_pct": round((v_weights["P2"] / total_weighted * 100.0) if total_weighted > 0 else 0.0, 2),
            "p3_weighted_pct": round((v_weights["P3"] / total_weighted * 100.0) if total_weighted > 0 else 0.0, 2),
            "p4_weighted_pct": round((v_weights["P4"] / total_weighted * 100.0) if total_weighted > 0 else 0.0, 2),
            "weighted_implied_ev": round(implied_ev, 4),
        })

    # 2. Voter Distribution Dot Map (dedup to latest stance per user)
    latest_user_rows = votes.sort_values("timestamp").groupby("author_username").last().reset_index()
    voter_distribution = []
    cohort_scores = {vt: [] for vt in vote_types}
    cohort_counts = {vt: 0 for vt in vote_types}

    for _, row in latest_user_rows.iterrows():
        vt = row["vote_type"]
        uname = row["author_username"]
        score = float(row["bayesian_score"])
        weight = float(row["power_weight"])

        if vt in cohort_scores:
            cohort_scores[vt].append(score)
            cohort_counts[vt] += 1

        voter_distribution.append({
            "author_username": uname,
            "vote_type": vt,
            "bayesian_accuracy_pct": round(score * 100.0, 2),
            "power_weight": round(weight, 4),
            "x_jitter": get_voter_jitter(uname),
        })

    # 3. Generalized Power-Mean RMS per Cohort
    p_exp = float(power_exponent)
    cohort_rms = {}
    for vt in vote_types:
        scores = cohort_scores[vt]
        if scores:
            mean_pow = np.mean([s**p_exp for s in scores])
            rms = float(mean_pow**(1.0 / p_exp))
            cohort_rms[vt] = round(rms, 4)
        else:
            cohort_rms[vt] = round(prior_score, 4)

    # 4. Chat messages stream
    chat_messages = []
    for _, row in votes.iterrows():
        urls_val = row.get("urls")
        if isinstance(urls_val, list):
            urls = urls_val
        elif isinstance(urls_val, str) and urls_val:
            import json
            try:
                urls = json.loads(urls_val)
            except Exception:
                urls = [u.strip() for u in urls_val.split(",") if u.strip()]
        else:
            urls = []

        ts_val = row["timestamp"]
        chat_messages.append({
            "message_id": str(row.get("message_id") or ""),
            "author_username": str(row.get("author_username") or ""),
            "timestamp": ts_val.isoformat() if hasattr(ts_val, "isoformat") else str(ts_val),
            "vote_type": str(row.get("vote_type") or "P2"),
            "content": str(row.get("content") or ""),
            "urls": urls,
            "bayesian_score": round(float(row["bayesian_score"]), 4),
            "power_weight": round(float(row["power_weight"]), 4),
        })

    final_ev = trajectory_events[-1]["weighted_implied_ev"] if trajectory_events else fallback_price

    return {
        "consensus_trajectory": trajectory_events,
        "voter_distribution": voter_distribution,
        "cohort_rms": cohort_rms,
        "cohort_counts": cohort_counts,
        "chat_messages": chat_messages,
        "implied_ev": final_ev,
    }
