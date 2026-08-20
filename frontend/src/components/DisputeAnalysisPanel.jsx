import React, { useState, useMemo } from "react";
import { 
  ResponsiveContainer, 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  Tooltip, 
  CartesianGrid, 
  ReferenceArea,
  ReferenceLine
} from "recharts";
import { 
  ExternalLink, 
  Flame, 
  CheckCircle2, 
  ArrowLeft,
  Radar,
  TrendingUp,
  Scale
} from "lucide-react";
import ConsensusReplayPanel from "./ConsensusReplayPanel";
import { formatUTC } from "./ScreenerTable";

export default function DisputeAnalysisPanel({
  marketDetail,
  onClose,
  minCompetencyPct,
}) {
  // Default to Tab A (Market Info & Macro Price) first
  const [subTab, setSubTab] = useState("market");

  if (!marketDetail) {
    return (
      <div className="rounded-xl border border-slate-800 bg-[#0e1524] p-10 text-center text-slate-400">
        Select a market from the screener to view in-depth dispute trajectories and analytics.
      </div>
    );
  }

  const {
    market_id,
    question,
    slug,
    description,
    market_status_code,
    yes_price,
    no_price,
    best_bid,
    best_bid_shares,
    best_ask,
    best_ask_shares,
    consensus_price_delta,
    dispute_rounds,
    price_history,
    consensus_trajectory,
    voter_distribution,
    cohort_rms,
    cohort_counts,
    chat_messages,
  } = marketDetail;

  const isLive = market_status_code === "LIVE_DISPUTE";

  let statusPill;
  if (isLive) {
    statusPill = (
      <span className="inline-flex items-center gap-1.5 rounded-md bg-cyan-500/20 px-2.5 py-1 font-mono text-xs font-bold text-cyan-300 border border-cyan-500/50 shadow-sm">
        <Flame className="h-3.5 w-3.5 text-cyan-400" />
        LIVE DISPUTE
      </span>
    );
  } else if (market_status_code === "RESOLVED_EARLY") {
    statusPill = (
      <span className="inline-flex items-center gap-1.5 rounded-md bg-purple-500/20 px-2.5 py-1 font-mono text-xs font-semibold text-purple-300 border border-purple-500/40">
        <AlertTriangle className="h-3.5 w-3.5" />
        RESOLVED EARLY (P4)
      </span>
    );
  } else if (market_status_code === "RESOLVED_P2") {
    statusPill = (
      <span className="inline-flex items-center gap-1.5 rounded-md bg-emerald-500/20 px-2.5 py-1 font-mono text-xs font-semibold text-emerald-300 border border-emerald-500/40">
        <CheckCircle2 className="h-3.5 w-3.5" />
        RESOLVED (YES - P2)
      </span>
    );
  } else {
    statusPill = (
      <span className="inline-flex items-center gap-1.5 rounded-md bg-rose-500/20 px-2.5 py-1 font-mono text-xs font-semibold text-rose-300 border border-rose-500/40">
        <CheckCircle2 className="h-3.5 w-3.5" />
        RESOLVED (NO - P1)
      </span>
    );
  }

  // Calculate latest round weighted consensus shares (same as Voter Distribution Chart)
  const latestShares = useMemo(() => {
    let p1 = 0, p2 = 0, p3 = 0, p4 = 0;
    if (consensus_trajectory && consensus_trajectory.length > 0) {
      const last = consensus_trajectory[consensus_trajectory.length - 1];
      p1 = last.p1_weighted_pct ?? (last.p1_pct ? last.p1_pct * 100 : 0);
      p2 = last.p2_weighted_pct ?? (last.p2_pct ? last.p2_pct * 100 : 0);
      p3 = last.p3_weighted_pct ?? (last.p3_pct ? last.p3_pct * 100 : 0);
      p4 = last.p4_weighted_pct ?? (last.p4_pct ? last.p4_pct * 100 : 0);
    } else if (cohort_counts) {
      const c1 = cohort_counts.P1 || 0;
      const c2 = cohort_counts.P2 || 0;
      const c3 = cohort_counts.P3 || 0;
      const c4 = cohort_counts.P4 || 0;
      const tot = c1 + c2 + c3 + c4;
      if (tot > 0) {
        p1 = (c1 / tot) * 100;
        p2 = (c2 / tot) * 100;
        p3 = (c3 / tot) * 100;
        p4 = (c4 / tot) * 100;
      }
    }

    const totalVotes = (cohort_counts?.P1 || 0) + (cohort_counts?.P2 || 0) + (cohort_counts?.P3 || 0) + (cohort_counts?.P4 || 0) || (voter_distribution?.length) || (dispute_rounds?.[dispute_rounds.length - 1]?.total_votes) || 0;

    const total = p1 + p2 + p3 + p4;
    if (total > 0) {
      const rawShares = [
        { key: "P2", label: "YES", pct: (p2 / total) * 100, color: "bg-emerald-500", textColor: "text-emerald-400" },
        { key: "P1", label: "NO", pct: (p1 / total) * 100, color: "bg-rose-500", textColor: "text-rose-400" },
        { key: "P3", label: "UNKNOWN", pct: (p3 / total) * 100, color: "bg-amber-500", textColor: "text-amber-400" },
        { key: "P4", label: "EARLY", pct: (p4 / total) * 100, color: "bg-purple-500", textColor: "text-purple-400" },
      ];
      const shares = rawShares.filter((s) => s.pct > 0);
      const winningKey = shares.length > 0 ? [...shares].sort((a, b) => b.pct - a.pct)[0].key : null;
      return { shares, winningKey, totalVotes };
    }
    return { shares: [], winningKey: null, totalVotes };
  }, [consensus_trajectory, cohort_counts, voter_distribution, dispute_rounds]);

  // Format macro price history and find day boundaries (00:00 marks)
  const { macroChartData, midnightLines, dateTickMap } = useMemo(() => {
    if (!price_history || price_history.length === 0) {
      return { macroChartData: [], midnightLines: [], dateTickMap: {} };
    }

    const seenDates = new Set();
    const midnights = [];
    const tickMap = {};

    const data = price_history.map((p) => {
      const d = new Date(p.timestamp);
      const day = String(d.getUTCDate()).padStart(2, "0");
      const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      const month = months[d.getUTCMonth()];
      const hours = String(d.getUTCHours()).padStart(2, "0");
      const minutes = String(d.getUTCMinutes()).padStart(2, "0");
      const dateKey = `${day} ${month}`;
      const uniqueKey = `${day} ${month} ${hours}:${minutes}:${d.getUTCSeconds()}`;

      // First point of a new day (closest to 00:00)
      if (!seenDates.has(dateKey)) {
        seenDates.add(dateKey);
        midnights.push(uniqueKey);
        tickMap[uniqueKey] = dateKey; // Maps uniqueKey -> "DD MMM"
      }

      return {
        timestamp: p.timestamp,
        timeFormatted: formatUTC(p.timestamp, true, false),
        uniqueKey: uniqueKey,
        dateLabel: dateKey,
        yes_price: p.yes_price,
      };
    });

    return { macroChartData: data, midnightLines: midnights, dateTickMap: tickMap };
  }, [price_history]);

  // Identify dispute round windows for yellow highlight & callouts
  const disputeAreas = useMemo(() => {
    if (!dispute_rounds || dispute_rounds.length === 0 || macroChartData.length === 0) return [];
    
    return dispute_rounds.map((r) => {
      const startMs = new Date(r.round_start).getTime();
      const endMs = new Date(r.round_end).getTime();

      let closestStart = macroChartData[0];
      let minStartDiff = Math.abs(new Date(closestStart.timestamp).getTime() - startMs);
      let closestEnd = macroChartData[macroChartData.length - 1];
      let minEndDiff = Math.abs(new Date(closestEnd.timestamp).getTime() - endMs);

      macroChartData.forEach((p) => {
        const t = new Date(p.timestamp).getTime();
        const startDiff = Math.abs(t - startMs);
        const endDiff = Math.abs(t - endMs);
        if (startDiff < minStartDiff) {
          minStartDiff = startDiff;
          closestStart = p;
        }
        if (endDiff < minEndDiff) {
          minEndDiff = endDiff;
          closestEnd = p;
        }
      });

      return {
        round_num: r.round_num,
        x1: closestStart.uniqueKey,
        x2: closestEnd.uniqueKey,
        startTimeFormatted: formatUTC(r.round_start, true, true),
      };
    });
  }, [dispute_rounds, macroChartData]);

  return (
    <div className="w-full space-y-4 transition-all">
      {/* ─── SECTION 1: HEADLINES BAR ─── */}
      <div className="rounded-xl border border-slate-800 bg-[#0e1524] p-4 shadow-md">
        <div className="flex items-start justify-between gap-4">
          {/* Left: Question & Meta */}
          <div className="space-y-1.5 max-w-4xl">
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={onClose}
                className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800 hover:text-white transition-all cursor-pointer font-sans"
                title="Back to Market Screener"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                <Radar className="h-3.5 w-3.5 text-slate-400" />
                <span className="text-[11px] font-medium">Screener</span>
              </button>
              {statusPill}
              <span className="font-mono text-xs text-slate-400">ID: #{market_id}</span>
            </div>

            <div className="flex items-center gap-2">
              <h2 className="text-base sm:text-lg font-bold text-slate-100 leading-snug">
                {question}
              </h2>
              {slug && (
                <a
                  href={`https://polymarket.com/market/${slug}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-slate-400 hover:text-slate-200 transition-colors p-1"
                  title="View on Polymarket"
                >
                  <ExternalLink className="h-4 w-4" />
                </a>
              )}
            </div>
          </div>
        </div>

        {/* ─── ORDERED HEADLINE NUMBERS STRIP ─── */}
        <div className="mt-3.5 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-12 gap-x-6 gap-y-3 pt-3 border-t border-slate-800/80 items-start">
          {/* 1. Trading Price (YES only) */}
          <div className="lg:col-span-2 space-y-1">
            <div className="h-4 flex items-center text-[11px] text-slate-400 font-medium">
              Trading Price
            </div>
            <div className="h-6 flex items-center gap-1.5 font-mono">
              <span className="text-sm font-bold text-cyan-400 leading-none">YES ${yes_price?.toFixed(3)}</span>
            </div>
          </div>

          {/* 2. Orderbook */}
          <div className="lg:col-span-4 space-y-1 col-span-2 sm:col-span-2">
            <div className="h-4 flex items-center text-[11px] text-slate-400 font-medium">
              Orderbook
            </div>
            <div className="h-6 flex items-center gap-2 font-mono text-xs">
              {/* Bid Pill (Darker Green) */}
              <span className="inline-flex items-center gap-1.5 rounded bg-emerald-950/70 border border-emerald-900/90 px-2 py-0.5 text-emerald-500 font-bold leading-none">
                <span>${best_bid?.toFixed(2)}</span>
                <span className="text-emerald-800 font-normal">·</span>
                <span className="text-slate-400 font-normal text-[11px]">{(best_bid_shares / 1000).toFixed(1)}k</span>
              </span>

              {/* Ask Pill (Darker Red) */}
              <span className="inline-flex items-center gap-1.5 rounded bg-rose-950/70 border border-rose-900/90 px-2 py-0.5 text-rose-500 font-bold leading-none">
                <span>${best_ask?.toFixed(2)}</span>
                <span className="text-rose-800 font-normal">·</span>
                <span className="text-slate-400 font-normal text-[11px]">{(best_ask_shares / 1000).toFixed(1)}k</span>
              </span>
            </div>
          </div>

          {/* 3. Dispute Vote Share (Outcome Pills with Pulsing Winning Vote) */}
          <div className="lg:col-span-4 space-y-1 col-span-2 sm:col-span-2">
            <div className="h-4 flex items-center gap-1.5 text-[11px] text-slate-400 font-medium">
              <span>Dispute Vote Share</span>
              {latestShares.totalVotes > 0 && (
                <span className="font-mono text-slate-500 text-[11px]">
                  ({latestShares.totalVotes} {latestShares.totalVotes === 1 ? "vote" : "votes"})
                </span>
              )}
            </div>
            {/* Outcome Badges with Pulsing Border on Winner */}
            <div className="h-6 flex items-center gap-1.5 text-xs font-mono">
              {latestShares.shares.map((s) => {
                const isWinner = s.key === latestShares.winningKey;
                return (
                  <span
                    key={s.key}
                    className={`inline-flex items-center gap-1.5 rounded px-2 py-0.5 leading-none transition-all ${
                      isWinner
                        ? "border border-cyan-400/90 bg-cyan-950/40 text-cyan-300 ring-1 ring-cyan-400/50 live-pulse-glow font-bold"
                        : "border border-slate-800 bg-slate-900/60 text-slate-400 font-medium"
                    }`}
                  >
                    <span className={`inline-block h-1.5 w-1.5 rounded-full ${s.color}`} />
                    <span className={isWinner ? "text-cyan-300" : s.textColor}>{s.label}</span>
                    <span className={isWinner ? "text-slate-200" : "text-slate-400"}>{s.pct.toFixed(0)}%</span>
                  </span>
                );
              })}
            </div>
          </div>

          {/* 4. Live Delta (Decimal 0.## format +/-) */}
          <div className="lg:col-span-2 space-y-1">
            <div className="h-4 flex items-center text-[11px] text-slate-400 font-medium">
              {isLive ? "Live Delta" : "Max Dispute Delta"}
            </div>
            <div className="h-6 flex items-center gap-1.5 font-mono">
              <span
                className={`text-sm font-bold leading-none ${
                  consensus_price_delta > 0
                    ? "text-emerald-400"
                    : consensus_price_delta < 0
                    ? "text-rose-400"
                    : "text-slate-400"
                }`}
              >
                {consensus_price_delta > 0
                  ? `+${consensus_price_delta.toFixed(2)}`
                  : consensus_price_delta < 0
                  ? `${consensus_price_delta.toFixed(2)}`
                  : "0.00"}
              </span>
              <span className="text-[11px] text-slate-500 font-sans leading-none">
                {consensus_price_delta > 0 ? "(BUY YES)" : consensus_price_delta < 0 ? "(BUY NO)" : "(Fair)"}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ─── SECTION 2: SUB-TAB NAVIGATION (TAB A FIRST, THEN TAB B) ─── */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => setSubTab("market")}
          className={`flex items-center gap-1.5 sm:gap-2 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
            subTab === "market"
              ? "text-slate-100 bg-slate-800/80 border border-slate-700 shadow-sm"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 border border-transparent"
          }`}
        >
          <TrendingUp className="h-3.5 w-3.5" />
          <span>Market Details</span>
        </button>

        <button
          onClick={() => setSubTab("dispute")}
          className={`flex items-center gap-1.5 sm:gap-2 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
            subTab === "dispute"
              ? "text-slate-100 bg-slate-800/80 border border-slate-700 shadow-sm"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 border border-transparent"
          }`}
        >
          <Scale className="h-3.5 w-3.5" />
          <span>Dispute Analytics</span>
        </button>
      </div>

      {/* ─── TAB A: MARKET INFO & MACRO PRICE ─── */}
      {subTab === "market" && (
        <div className="grid grid-cols-1 lg:grid-cols-10 gap-4 animate-in fade-in duration-200">
          {/* Key Info Panel (40%) */}
          <div className="lg:col-span-4 rounded-xl border border-slate-800 bg-[#0e1524] p-4 space-y-4 shadow-md">
            <div>
              <h4 className="text-xs font-bold text-slate-200 mb-2">
                Description
              </h4>
              <div className="rounded-lg bg-slate-950/80 p-3 border border-slate-800 text-xs text-slate-300 font-sans leading-relaxed whitespace-pre-line max-h-[300px] overflow-y-auto">
                {description || "No description provided for this market."}
              </div>
            </div>

            {/* Dispute Rounds Breakdown */}
            <div>
              <h4 className="text-xs font-bold text-slate-200 mb-2">
                Dispute History
              </h4>
              <div className="space-y-2">
                {(dispute_rounds || []).map((r) => (
                  <div
                    key={r.round_num}
                    className="rounded-lg bg-slate-900/60 p-2.5 border border-slate-800 text-xs space-y-1"
                  >
                    <div className="flex items-center justify-between font-mono">
                      <span className="font-bold text-slate-200">Round {r.round_num}</span>
                      <span className="text-[10px] text-slate-500">{r.total_votes} votes</span>
                    </div>
                    <div className="text-[11px] text-slate-400 font-mono">
                      {formatUTC(r.round_start, true, true)} → {formatUTC(r.round_end, true, true)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Macro Price Chart with Vertical Grid at 00:00, Yellow Dispute Window (60%) */}
          <div className="lg:col-span-6 rounded-xl border border-slate-800 bg-[#0e1524] p-4 space-y-3 shadow-md flex flex-col">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold text-slate-200">
                Price History
              </h4>
              <div className="flex items-center gap-1.5 text-xs font-mono text-cyan-400">
                <span className="h-2 w-2 rounded-full bg-cyan-400"></span>
                <span>YES Price (USD)</span>
              </div>
            </div>

            <div className="flex-1 w-full min-h-[340px] bg-slate-950/60 rounded-lg border border-slate-800 p-2">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={macroChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={true} vertical={true} />
                  
                  {/* X-Axis displaying only DD MMM */}
                  <XAxis
                    dataKey="uniqueKey"
                    ticks={midnightLines}
                    tickFormatter={(val) => dateTickMap[val] || val.split(" ").slice(0, 2).join(" ")}
                    stroke="#64748b"
                    fontSize={9.5}
                    tickLine={false}
                    axisLine={{ stroke: "#334155" }}
                  />
                  <YAxis
                    stroke="#64748b"
                    fontSize={9.5}
                    domain={[0, 1]}
                    ticks={[0.0, 0.2, 0.4, 0.6, 0.8, 1.0]}
                    tickFormatter={(v) => `$${v.toFixed(2)}`}
                    tickLine={false}
                    axisLine={{ stroke: "#334155" }}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload;
                        return (
                          <div className="rounded-lg border border-slate-700 bg-slate-900/95 p-2 shadow-2xl text-xs font-mono">
                            <div className="text-slate-400">{data.timeFormatted}</div>
                            <div className="font-bold text-emerald-400">YES Price: ${data.yes_price?.toFixed(3)}</div>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />

                  {/* Vertical Grid Lines at 00:00 Day Boundaries */}
                  {midnightLines.map((mKey) => (
                    <ReferenceLine
                      key={`midnight-${mKey}`}
                      x={mKey}
                      stroke="#1e293b"
                      strokeDasharray="2 2"
                      strokeWidth={1}
                    />
                  ))}

                  {/* Yellow Shaded Dispute Window (No dotted line or callout text) */}
                  {disputeAreas.map((da) => (
                    <ReferenceArea
                      key={da.round_num}
                      x1={da.x1}
                      x2={da.x2}
                      fill="#f59e0b"
                      fillOpacity={0.22}
                      stroke="none"
                    />
                  ))}

                  <Line
                    type="stepAfter"
                    dataKey="yes_price"
                    stroke="#06b6d4"
                    strokeWidth={1.4}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* ─── TAB B: DISPUTE ANALYTICS & DISCOURSE (SINGLE-ROW COMPRESSED LAYOUT) ─── */}
      {subTab === "dispute" && (
        <div className="animate-in fade-in duration-200">
          <ConsensusReplayPanel
            consensusTrajectory={consensus_trajectory || []}
            priceHistory={price_history || []}
            chatMessages={chat_messages || []}
            voterDistribution={voter_distribution || []}
            cohortRms={cohort_rms || {}}
            cohortCounts={cohort_counts || {}}
            minCompetencyPct={minCompetencyPct}
          />
        </div>
      )}
    </div>
  );
}
