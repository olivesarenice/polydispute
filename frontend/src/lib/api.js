/**
 * HTTP API client for Polydispute backend.
 * 
 * Strict Zero-Mock Policy:
 * Throws explicit errors when network or MotherDuck connection drops.
 * Does NOT fall back to local mock fixtures.
 */

const API_BASE = "";

/**
 * Fetch live system health, MotherDuck connection state, latency, and cache metrics.
 * @returns {Promise<{ status: string, database: string, database_target: string, motherduck_latency_ms: number, cached_markets_count: number, version: string, timestamp: string }>}
 */
export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/api/health`, {
    headers: { "Accept": "application/json" }
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Health check failed (${res.status}): ${text || res.statusText}`);
  }
  return res.json();
}

/**
 * Fetch screener prediction markets.
 * @param {Object} options
 * @param {'live' | 'all' | 'resolved'} [options.status='live']
 * @param {number} [options.minVoters=10]
 * @param {string} [options.search]
 * @param {string} [options.sortBy='latest_dispute_started']
 * @param {'asc' | 'desc'} [options.sortDir='desc']
 * @param {number} [options.limit=500]
 */
export async function fetchScreenerMarkets({
  status = "live",
  minVoters = 0,
  search = "",
  sortBy = "latest_dispute_started",
  sortDir = "desc",
  limit = 3000
} = {}) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (minVoters > 0) params.set("min_voters", String(minVoters));
  if (search) params.set("search", search);
  if (sortBy) params.set("sort_by", sortBy);
  if (sortDir) params.set("sort_dir", sortDir);
  if (limit) params.set("limit", String(limit));

  const res = await fetch(`${API_BASE}/api/markets?${params.toString()}`, {
    headers: { "Accept": "application/json" }
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Failed to fetch screener markets (${res.status}): ${text || res.statusText}`);
  }
  return res.json();
}

/**
 * Fetch full analytical detail for a selected prediction market.
 * @param {string} marketId
 * @param {Object} [settings]
 * @param {number} [settings.trustNumber=20]
 * @param {number} [settings.priorScore=0.50]
 * @param {number} [settings.powerExponent=2.0]
 * @param {number} [settings.minAccuracy=0.0]
 */
export async function fetchMarketDetail(marketId, {
  trustNumber = 20,
  priorScore = 0.50,
  powerExponent = 2.0,
  minAccuracy = 0.0
} = {}) {
  const params = new URLSearchParams({
    trust_number: String(trustNumber),
    prior_score: String(priorScore),
    power_exponent: String(powerExponent),
    min_accuracy: String(minAccuracy)
  });

  const res = await fetch(`${API_BASE}/api/markets/${encodeURIComponent(marketId)}/detail?${params.toString()}`, {
    headers: { "Accept": "application/json" }
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Failed to fetch market detail for #${marketId} (${res.status}): ${text || res.statusText}`);
  }
  return res.json();
}

/**
 * Fetch voter calibration leaderboard.
 * @param {Object} [options]
 * @param {number} [options.minPredictions=5]
 * @param {number} [options.minCompetencyPct=50.0]
 * @param {number} [options.limit=100]
 */
export async function fetchLeaderboard({
  minPredictions = 5,
  minCompetencyPct = 50.0,
  limit = 1000
} = {}) {
  const params = new URLSearchParams({
    min_predictions: String(minPredictions),
    min_competency_pct: String(minCompetencyPct),
    limit: String(limit)
  });

  const res = await fetch(`${API_BASE}/api/leaderboard?${params.toString()}`, {
    headers: { "Accept": "application/json" }
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Failed to fetch leaderboard (${res.status}): ${text || res.statusText}`);
  }
  return res.json();
}
