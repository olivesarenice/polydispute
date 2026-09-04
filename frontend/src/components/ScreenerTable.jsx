import React, { useState, useMemo } from "react";
import { 
  ExternalLink, 
  Search, 
  Flame, 
  ArrowUp, 
  ArrowDown, 
  CheckCircle2, 
  TriangleAlert as AlertTriangle,
  Clock,
  SlidersHorizontal,
  Layers,
  Users
} from "lucide-react";

// Format helper for timestamps (DD MMM YYYY, HH:mm UTC)
export function formatUTC(isoString, includeTime = true, shortTime = false) {
  if (!isoString) return "—";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "—";
    
    const day = String(d.getUTCDate()).padStart(2, "0");
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const month = months[d.getUTCMonth()];
    const year = d.getUTCFullYear();
    
    const hours = String(d.getUTCHours()).padStart(2, "0");
    const minutes = String(d.getUTCMinutes()).padStart(2, "0");

    if (shortTime) {
      return `${day} ${month} ${hours}:${minutes}`;
    }
    
    if (!includeTime) {
      return `${day} ${month} ${year}`;
    }
    
    return `${day} ${month} ${year}, ${hours}:${minutes} UTC`;
  } catch (e) {
    return "—";
  }
}

// Relative time helper ("X hours/days ago")
export function formatRelativeTime(isoString) {
  if (!isoString) return "—";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "—";
    const now = new Date();
    const diffMs = now - d;
    if (diffMs < 0) return "Just now";
    
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHours = Math.floor(diffMin / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffSec < 60) return "Just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays === 1) return "1d ago";
    if (diffDays < 30) return `${diffDays}d ago`;
    const diffMonths = Math.floor(diffDays / 30);
    return `${diffMonths}mo ago`;
  } catch (e) {
    return "—";
  }
}

// Thinner, sleek Micro SVG Sparkline for live disputes
function Sparkline({ isLive, currentPrice }) {
  if (!isLive) {
    return <span className="text-slate-600 font-mono text-[10px] select-none">—</span>;
  }

  const base = Math.max(0.05, Math.min(0.95, currentPrice));
  const points = [
    Math.max(0.01, base - 0.07),
    Math.max(0.01, base - 0.03),
    Math.max(0.01, base + 0.02),
    Math.max(0.01, base - 0.01),
    Math.max(0.01, base + 0.02),
    base
  ];

  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 0.1;

  const width = 48;
  const height = 14;
  const step = width / (points.length - 1);

  const coords = points.map((p, idx) => {
    const x = idx * step;
    const y = height - ((p - min) / range) * (height - 3) - 1.5;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const pathD = `M ${coords.join(" L ")}`;
  const isUp = points[points.length - 1] >= points[0];
  const strokeColor = isUp ? "#34d399" : "#fb7185";

  return (
    <div className="flex items-center" title={`Trend: ending at $${currentPrice.toFixed(2)}`}>
      <svg width={width} height={height} className="overflow-visible">
        <path
          d={pathD}
          fill="none"
          stroke={strokeColor}
          strokeWidth="1.1"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle
          cx={coords[coords.length - 1].split(",")[0]}
          cy={coords[coords.length - 1].split(",")[1]}
          r="1.5"
          fill={strokeColor}
        />
      </svg>
    </div>
  );
}

// Visual Voter Density Representation (number + visual turnout meter)
function VoterVisualBadge({ count }) {
  // Turnout gauge scaled to 25 voters max
  const pct = Math.min(100, Math.max(10, Math.round((count / 25) * 100)));
  const barColor = 
    count >= 15 ? "bg-emerald-400" :
    count >= 7 ? "bg-cyan-400" :
    count >= 3 ? "bg-cyan-600" : "bg-slate-600";

  return (
    <div className="inline-flex flex-col items-center gap-1 py-0.5">
      <div className="flex items-center gap-1 font-mono text-xs font-semibold text-slate-200">
        <Users className="h-2.5 w-2.5 text-slate-500" />
        <span>{count}</span>
      </div>
      <div className="h-1 w-9 rounded-full bg-slate-800/90 overflow-hidden border border-slate-700/50">
        <div 
          className={`h-full rounded-full transition-all duration-300 ${barColor}`} 
          style={{ width: `${pct}%` }} 
        />
      </div>
    </div>
  );
}

export default function ScreenerTable({
  markets,
  selectedMarketId,
  onSelectMarket,
}) {
  const [searchQuery, setSearchQuery] = useState("");
  // Default to Live Disputes ONLY
  const [onlyLiveDisputes, setOnlyLiveDisputes] = useState(true);
  const [minVotersFilter, setMinVotersFilter] = useState(0);
  const [sortField, setSortField] = useState("latest_dispute_started");
  const [sortDirection, setSortDirection] = useState("desc");
  
  // Hover state tracking for popups
  const [hoveredMarketId, setHoveredMarketId] = useState(null);
  const [hoveredDisputeDateId, setHoveredDisputeDateId] = useState(null);
  const [hoveredClosedDateId, setHoveredClosedDateId] = useState(null);

  // Handle Sort Toggle
  const handleSort = (field) => {
    if (sortField === field) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  };

  // Filter & Sort Logic
  const filteredMarkets = useMemo(() => {
    return markets
      .filter((m) => {
        if (onlyLiveDisputes && !m.is_live_dispute) {
          return false;
        }
        if (m.total_voters < minVotersFilter) {
          return false;
        }
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase();
          const matchesQ = m.question?.toLowerCase().includes(q);
          const matchesId = m.market_id?.toLowerCase().includes(q);
          if (!matchesQ && !matchesId) return false;
        }
        return true;
      })
      .sort((a, b) => {
        let valA = a[sortField];
        let valB = b[sortField];

        // Date sorting
        if (sortField.includes("time") || sortField.includes("started")) {
          const timeA = valA ? new Date(valA).getTime() : 0;
          const timeB = valB ? new Date(valB).getTime() : 0;
          return sortDirection === "asc" ? timeA - timeB : timeB - timeA;
        }

        // Numeric sorting
        if (typeof valA === "number" && typeof valB === "number") {
          return sortDirection === "asc" ? valA - valB : valB - valA;
        }

        // String fallback
        valA = String(valA || "").toLowerCase();
        valB = String(valB || "").toLowerCase();
        return sortDirection === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
      });
  }, [markets, searchQuery, onlyLiveDisputes, minVotersFilter, sortField, sortDirection]);

  const liveCount = useMemo(() => markets.filter((m) => m.is_live_dispute).length, [markets]);
  const totalCount = markets.length;

  return (
    <div className="w-full space-y-3 transition-all duration-300">
      {/* Top Filter & Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 py-1">
        {/* Left: View Tabs (Live vs All) + Search */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Segmented Mode Toggle */}
          <div className="flex items-center rounded-lg border border-slate-800 bg-[#0d1322] p-1 shadow-inner">
            <button
              onClick={() => setOnlyLiveDisputes(true)}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-semibold transition-all ${
                onlyLiveDisputes
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Flame className="h-3.5 w-3.5 text-cyan-400" />
              <span>Live Disputes</span>
              <span className={`ml-1 rounded-full px-1.5 py-0.2 text-[10px] font-mono ${
                onlyLiveDisputes ? "bg-cyan-400/20 text-cyan-200" : "bg-slate-800 text-slate-400"
              }`}>
                {liveCount}
              </span>
            </button>

            <button
              onClick={() => setOnlyLiveDisputes(false)}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-semibold transition-all ${
                !onlyLiveDisputes
                  ? "bg-slate-800 text-slate-100 border border-slate-700 shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Layers className="h-3.5 w-3.5 text-slate-400" />
              <span>All Markets</span>
              <span className="ml-1 rounded-full bg-slate-800 px-1.5 py-0.2 text-[10px] font-mono text-slate-400">
                {totalCount}
              </span>
            </button>
          </div>

          {/* Search Box */}
          <div className="relative min-w-[220px] max-w-xs">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search markets or IDs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-lg border border-slate-800 bg-[#0d1322] pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 transition-all font-sans"
            />
          </div>
        </div>

        {/* Right: Minimum Voters Slider */}
        <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-[#0d1322] px-3 py-1 text-xs text-slate-400">
          <SlidersHorizontal className="h-3 w-3 text-slate-500" />
          <span className="text-[11px] font-medium text-slate-400">Min Voters:</span>
          <span className="font-mono font-bold text-slate-200 min-w-[14px]">{minVotersFilter}</span>
          <input
            type="range"
            min="0"
            max="25"
            value={minVotersFilter}
            onChange={(e) => setMinVotersFilter(Number(e.target.value))}
            className="h-1 w-20 cursor-pointer accent-cyan-500 bg-slate-800 rounded-lg"
          />
        </div>
      </div>

      {/* Streamlined Table Viewport */}
      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-[#0d1322] shadow-xl">
        <table className="w-full text-left text-xs text-slate-300">
          <thead className="border-b border-slate-800 bg-slate-900/60 font-mono text-[11px] uppercase tracking-wider text-slate-400">
            <tr>
              {/* 1. Market Question (with Market ID hover popup) */}
              <th
                onClick={() => handleSort("question")}
                className="py-2.5 px-4 cursor-pointer hover:text-slate-200 transition-colors min-w-[320px]"
              >
                <div className="flex items-center gap-1">
                  <span>Market</span>
                  {sortField === "question" && (sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                </div>
              </th>

              {/* 2. Status */}
              <th
                onClick={() => handleSort("market_status_code")}
                className="py-2.5 px-3 cursor-pointer hover:text-slate-200 transition-colors min-w-[110px]"
              >
                <div className="flex items-center gap-1">
                  <span>Status</span>
                  {sortField === "market_status_code" && (sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                </div>
              </th>

              {/* 3. YES Price + Thinner Sparkline */}
              <th
                onClick={() => handleSort("yes_price")}
                className="py-2.5 px-4 cursor-pointer hover:text-slate-200 transition-colors min-w-[140px]"
              >
                <div className="flex items-center gap-1">
                  <span className="text-emerald-400 font-semibold">YES Price</span>
                  {sortField === "yes_price" && (sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                </div>
              </th>

              {/* 4. Predominant Vote */}
              <th
                onClick={() => handleSort("predominant_vote")}
                className="py-2.5 px-3 cursor-pointer hover:text-slate-200 transition-colors min-w-[130px]"
              >
                <div className="flex items-center gap-1">
                  <span>Consensus</span>
                  {sortField === "predominant_vote" && (sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                </div>
              </th>

              {/* 5. Total Voters (Visual Turnout Meter) */}
              <th
                onClick={() => handleSort("total_voters")}
                className="py-2.5 px-3 cursor-pointer hover:text-slate-200 transition-colors text-center min-w-[90px]"
              >
                <div className="flex items-center justify-center gap-1">
                  <span>Voters</span>
                  {sortField === "total_voters" && (sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                </div>
              </th>

              {/* 6. Dispute Started (Relative time with hover popup) */}
              <th
                onClick={() => handleSort("latest_dispute_started")}
                className="py-2.5 px-3 cursor-pointer hover:text-slate-200 transition-colors min-w-[130px]"
              >
                <div className="flex items-center gap-1">
                  <span>Dispute Started</span>
                  {sortField === "latest_dispute_started" && (sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                </div>
              </th>

              {/* 7. Dedicated Closed Time (with hover popup) */}
              <th
                onClick={() => handleSort("market_closed_time")}
                className="py-2.5 px-4 cursor-pointer hover:text-slate-200 transition-colors min-w-[130px] text-right"
              >
                <div className="flex items-center justify-end gap-1">
                  <span>Closed Time</span>
                  {sortField === "market_closed_time" && (sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                </div>
              </th>
            </tr>
          </thead>

          <tbody className="divide-y divide-slate-800/60 font-sans">
            {filteredMarkets.length === 0 ? (
              <tr>
                <td colSpan="7" className="py-12 text-center text-slate-500">
                  {onlyLiveDisputes
                    ? "No live disputes active at this moment. Toggle 'All Markets' to view historical disputes."
                    : "No prediction markets match the selected filter criteria."}
                </td>
              </tr>
            ) : (
              filteredMarkets.map((m) => {
                const isSelected = m.market_id === selectedMarketId;
                const isLive = m.is_live_dispute;

                let statusBadge;
                if (isLive) {
                  statusBadge = (
                    <span className="inline-flex items-center gap-1 rounded-md bg-cyan-500/15 px-2 py-0.5 font-mono text-[10px] font-bold text-cyan-300 border border-cyan-500/40">
                      <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-ping"></span>
                      LIVE
                    </span>
                  );
                } else if (m.market_status_code === "RESOLVED_EARLY") {
                  statusBadge = (
                    <span className="inline-flex items-center gap-1 rounded-md bg-purple-500/15 px-2 py-0.5 font-mono text-[10px] font-semibold text-purple-300 border border-purple-500/30">
                      <AlertTriangle className="h-3 w-3" />
                      TOO EARLY (P4)
                    </span>
                  );
                } else if (m.market_status_code === "RESOLVED_P2") {
                  statusBadge = (
                    <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/15 px-2 py-0.5 font-mono text-[10px] font-semibold text-emerald-300 border border-emerald-500/30">
                      <CheckCircle2 className="h-3 w-3" />
                      RESOLVED (P2)
                    </span>
                  );
                } else if (m.market_status_code === "RESOLVED_P1") {
                  statusBadge = (
                    <span className="inline-flex items-center gap-1 rounded-md bg-rose-500/15 px-2 py-0.5 font-mono text-[10px] font-semibold text-rose-300 border border-rose-500/30">
                      <CheckCircle2 className="h-3 w-3" />
                      RESOLVED (P1)
                    </span>
                  );
                } else {
                  statusBadge = (
                    <span className="inline-flex items-center gap-1 rounded-md bg-slate-800 px-2 py-0.5 font-mono text-[10px] text-slate-400 border border-slate-700">
                      {m.market_status_label}
                    </span>
                  );
                }

                let predomColor = "text-slate-300";
                if (m.predominant_vote.includes("YES")) predomColor = "text-emerald-400 font-semibold";
                else if (m.predominant_vote.includes("NO")) predomColor = "text-rose-400 font-semibold";
                else if (m.predominant_vote.includes("EARLY")) predomColor = "text-purple-400 font-semibold";

                return (
                  <tr
                    key={m.market_id}
                    className={`transition-colors cursor-pointer group/row ${
                      isSelected
                        ? "bg-cyan-950/30 border-l-4 border-l-cyan-400"
                        : isLive
                        ? "bg-cyan-950/20 border-l-4 border-l-cyan-400 hover:bg-cyan-950/35"
                        : "hover:bg-slate-800/40"
                    }`}
                    onClick={() => onSelectMarket(m.market_id)}
                  >
                    {/* 1. Market Question with Hover Popup for Market ID */}
                    <td className="py-3 px-4 text-slate-200">
                      <div 
                        className="relative flex items-center gap-1.5"
                        onMouseEnter={() => setHoveredMarketId(m.market_id)}
                        onMouseLeave={() => setHoveredMarketId(null)}
                      >
                        <span className="font-medium text-slate-100 group-hover/row:text-cyan-300 transition-colors line-clamp-1 max-w-xl">
                          {m.question}
                        </span>

                        {m.slug && (
                          <a
                            href={`https://polymarket.com/market/${m.slug}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="text-slate-500 hover:text-cyan-400 transition-colors opacity-40 group-hover/row:opacity-100 flex-shrink-0"
                            title="View on Polymarket"
                          >
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        )}

                        {/* Hover Popup showing Market ID */}
                        {hoveredMarketId === m.market_id && (
                          <div className="absolute left-0 -top-8 z-30 flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1 text-[11px] font-mono text-slate-300 shadow-xl pointer-events-none animate-in fade-in duration-150">
                            <span className="text-slate-500">ID:</span>
                            <span className="font-semibold text-cyan-300">{m.market_id}</span>
                          </div>
                        )}
                      </div>
                    </td>

                    {/* 2. Status Badge */}
                    <td className="py-3 px-3">{statusBadge}</td>

                    {/* 3. YES Price (2 d.p.) + Thinner Sparkline */}
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2.5">
                        <span className="font-mono font-bold text-sm text-emerald-400 min-w-[42px]">
                          ${m.yes_price.toFixed(2)}
                        </span>
                        <Sparkline isLive={isLive} currentPrice={m.yes_price} />
                      </div>
                    </td>

                    {/* 4. Predominant Vote / Consensus */}
                    <td className={`py-3 px-3 font-mono text-xs ${predomColor}`}>
                      {m.predominant_vote}
                    </td>

                    {/* 5. Total Voters (Visual Turnout Meter) */}
                    <td className="py-3 px-3 text-center font-mono">
                      <VoterVisualBadge count={m.total_voters} />
                    </td>

                    {/* 6. Dispute Started (Relative time with Hover Popup) */}
                    <td className="py-3 px-3 font-mono text-xs text-slate-400">
                      <div 
                        className="relative inline-block cursor-help"
                        onMouseEnter={() => setHoveredDisputeDateId(m.market_id)}
                        onMouseLeave={() => setHoveredDisputeDateId(null)}
                      >
                        <span className="hover:text-slate-200 transition-colors">
                          {formatRelativeTime(m.latest_dispute_started)}
                        </span>

                        {/* Hover Popup showing exact UTC Timestamp */}
                        {hoveredDisputeDateId === m.market_id && m.latest_dispute_started && (
                          <div className="absolute left-1/2 -translate-x-1/2 -top-8 z-30 flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1 text-[11px] font-mono text-cyan-300 shadow-xl whitespace-nowrap pointer-events-none animate-in fade-in duration-150">
                            <Clock className="h-3 w-3 text-slate-400" />
                            <span>{formatUTC(m.latest_dispute_started, true, false)}</span>
                          </div>
                        )}
                      </div>
                    </td>

                    {/* 7. Dedicated Closed Time (with Hover Popup) */}
                    <td className="py-3 px-4 text-right font-mono text-xs text-slate-400">
                      {m.market_closed_time ? (
                        <div 
                          className="relative inline-block cursor-help"
                          onMouseEnter={() => setHoveredClosedDateId(m.market_id)}
                          onMouseLeave={() => setHoveredClosedDateId(null)}
                        >
                          <span className="hover:text-slate-200 transition-colors">
                            {formatRelativeTime(m.market_closed_time)}
                          </span>

                          {/* Hover Popup showing exact Closed UTC Timestamp */}
                          {hoveredClosedDateId === m.market_id && (
                            <div className="absolute right-0 -top-8 z-30 flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1 text-[11px] font-mono text-purple-300 shadow-xl whitespace-nowrap pointer-events-none animate-in fade-in duration-150">
                              <Clock className="h-3 w-3 text-slate-400" />
                              <span>{formatUTC(m.market_closed_time, true, false)}</span>
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
