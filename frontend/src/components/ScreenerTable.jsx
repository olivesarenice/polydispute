import React, { useState, useMemo } from "react";
import { 
  BarChart2, 
  ExternalLink, 
  Search, 
  Flame, 
  ArrowUp, 
  ArrowDown, 
  CheckCircle2, 
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  SlidersHorizontal
} from "lucide-react";

// Format helper for timestamps (DD MMM YYYY, HH:mm UTC or DD MMM HH:mm)
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

export default function ScreenerTable({
  markets,
  selectedMarketId,
  onSelectMarket,
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [onlyLiveDisputes, setOnlyLiveDisputes] = useState(false);
  const [minVotersFilter, setMinVotersFilter] = useState(5);
  const [sortField, setSortField] = useState("latest_dispute_started");
  const [sortDirection, setSortDirection] = useState("desc");

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
        // 1. Live Dispute Filter
        if (onlyLiveDisputes && !m.is_live_dispute) {
          return false;
        }
        // 2. Minimum Voters Filter
        if (m.total_voters < minVotersFilter) {
          return false;
        }
        // 3. Search Query (Question or Market ID)
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

  return (
    <div className="w-full space-y-3 transition-all duration-300">
      {/* Control Bar (Unboxed) */}
      <div className="flex flex-wrap items-center justify-between gap-3 py-1">
        {/* Left: Search & Filter Toggles */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Search Box */}
          <div className="relative min-w-[260px] max-w-sm">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search question or market ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950/80 py-1.5 pl-9 pr-3 text-xs text-slate-200 placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
            />
          </div>

          {/* Live Disputes Toggle Button */}
          <button
            onClick={() => setOnlyLiveDisputes(!onlyLiveDisputes)}
            className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all border ${
              onlyLiveDisputes
                ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/50 shadow-sm"
                : "bg-slate-900 text-slate-300 border-slate-700 hover:border-slate-600 hover:text-white"
            }`}
          >
            <Flame className={`h-3.5 w-3.5 ${onlyLiveDisputes ? "text-cyan-400 animate-pulse" : "text-slate-400"}`} />
            <span>Live Disputes</span>
            <span className="rounded bg-slate-800 px-1.5 py-0.2 text-[10px] font-mono text-cyan-300 border border-slate-700">
              {liveCount}
            </span>
          </button>

          {/* Min Voters Slider Pill */}
          <div className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-slate-300">
            <SlidersHorizontal className="h-3 w-3 text-slate-400" />
            <span className="text-slate-400 font-medium">Min Voters:</span>
            <span className="font-mono font-bold text-emerald-400">{minVotersFilter}</span>
            <input
              type="range"
              min="0"
              max="30"
              step="1"
              value={minVotersFilter}
              onChange={(e) => setMinVotersFilter(parseInt(e.target.value, 10))}
              className="w-20 accent-emerald-500 h-1 bg-slate-800 rounded cursor-pointer"
            />
          </div>
        </div>

        {/* Right: Results Count */}
        <div className="flex items-center gap-3">
          <div className="text-xs text-slate-400 font-mono">
            Showing <span className="font-semibold text-slate-200">{filteredMarkets.length.toLocaleString()}</span> / <span className="text-slate-400">{markets.length.toLocaleString()}</span> markets
          </div>
        </div>
      </div>

      {/* Screener Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-[#0e1524] shadow-xl transition-all duration-300 max-h-[calc(100vh-220px)] overflow-y-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead className="sticky top-0 z-20 border-b border-slate-800 bg-slate-900/95 backdrop-blur-md text-[11px] font-mono uppercase tracking-wider text-slate-400">
            <tr>
              <th className="py-2.5 pl-3 pr-2 w-12 text-center"></th>
              
              <th
                onClick={() => handleSort("market_id")}
                className="py-2.5 px-3 cursor-pointer hover:text-slate-200 transition-colors"
              >
                <div className="flex items-center gap-1">
                  <span>Market ID</span>
                  {sortField === "market_id" && (sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                </div>
              </th>

              <th
                onClick={() => handleSort("question")}
                className="py-2.5 px-3 cursor-pointer hover:text-slate-200 transition-colors min-w-[280px]"
              >
                <div className="flex items-center gap-1">
                  <span>Question</span>
                  {sortField === "question" && (sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                </div>
              </th>

              <th
                onClick={() => handleSort("market_status_code")}
                className="py-2.5 px-3 cursor-pointer hover:text-slate-200 transition-colors"
              >
                <div className="flex items-center gap-1">
                  <span>Status</span>
                  {sortField === "market_status_code" && (sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                </div>
              </th>

              <th
                onClick={() => handleSort("latest_dispute_started")}
                className="py-2.5 px-3 cursor-pointer hover:text-slate-200 transition-colors min-w-[160px]"
              >
                <div className="flex items-center gap-1">
                  <span>Dispute Started</span>
                  {sortField === "latest_dispute_started" && (sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                </div>
              </th>

              <th
                onClick={() => handleSort("market_closed_time")}
                className="py-2.5 px-3 cursor-pointer hover:text-slate-200 transition-colors min-w-[140px]"
              >
                <div className="flex items-center gap-1">
                  <span>Closed Time</span>
                  {sortField === "market_closed_time" && (sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                </div>
              </th>

              <th
                onClick={() => handleSort("yes_price")}
                className="py-2.5 px-3 cursor-pointer hover:text-slate-200 transition-colors text-right"
              >
                <div className="flex items-center justify-end gap-1">
                  <span className="text-emerald-400">YES Price</span>
                  {sortField === "yes_price" && (sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                </div>
              </th>

              <th
                onClick={() => handleSort("no_price")}
                className="py-2.5 px-3 cursor-pointer hover:text-slate-200 transition-colors text-right"
              >
                <div className="flex items-center justify-end gap-1">
                  <span className="text-rose-400">NO Price</span>
                  {sortField === "no_price" && (sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                </div>
              </th>

              <th
                onClick={() => handleSort("total_voters")}
                className="py-2.5 px-3 cursor-pointer hover:text-slate-200 transition-colors text-center"
              >
                <div className="flex items-center justify-center gap-1">
                  <span>Voters</span>
                  {sortField === "total_voters" && (sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                </div>
              </th>

              <th
                onClick={() => handleSort("predominant_vote")}
                className="py-2.5 px-3 cursor-pointer hover:text-slate-200 transition-colors min-w-[130px]"
              >
                <div className="flex items-center gap-1">
                  <span>Predominant Vote</span>
                  {sortField === "predominant_vote" && (sortDirection === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                </div>
              </th>
            </tr>
          </thead>

          <tbody className="divide-y divide-slate-800/60 font-sans">
            {filteredMarkets.length === 0 ? (
              <tr>
                <td colSpan="10" className="py-10 text-center text-slate-500">
                  No prediction markets match the selected filter criteria.
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
                      LIVE DISPUTE
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
                      RESOLVED (YES - P2)
                    </span>
                  );
                } else if (m.market_status_code === "RESOLVED_P1") {
                  statusBadge = (
                    <span className="inline-flex items-center gap-1 rounded-md bg-rose-500/15 px-2 py-0.5 font-mono text-[10px] font-semibold text-rose-300 border border-rose-500/30">
                      <CheckCircle2 className="h-3 w-3" />
                      RESOLVED (NO - P1)
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
                    className={`transition-colors cursor-pointer ${
                      isSelected
                        ? "bg-emerald-950/30 border-l-4 border-l-emerald-500"
                        : isLive
                        ? "bg-cyan-950/20 border-l-4 border-l-cyan-400 hover:bg-cyan-950/40"
                        : "hover:bg-slate-800/40"
                    }`}
                    onClick={() => onSelectMarket(m.market_id)}
                  >
                    {/* Action Icon on left */}
                    <td className="py-2.5 pl-3 pr-2 text-center">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectMarket(m.market_id);
                        }}
                        className={`flex h-7 w-7 items-center justify-center rounded-lg border transition-all mx-auto ${
                          isSelected
                            ? "bg-emerald-500 text-slate-950 border-emerald-400 shadow-sm font-bold"
                            : "border-slate-700 bg-slate-900 text-slate-300 hover:border-emerald-500 hover:text-emerald-300"
                        }`}
                        title="Inspect Trajectory"
                      >
                        <BarChart2 className="h-3.5 w-3.5" />
                      </button>
                    </td>

                    {/* Market ID */}
                    <td className="py-2.5 px-3 font-mono font-medium text-slate-400 text-[11px]">
                      {m.market_id}
                    </td>

                    {/* Question */}
                    <td className="py-2.5 px-3 text-slate-200">
                      <div className="flex items-center gap-1.5 group">
                        <span className="font-medium hover:text-emerald-300 transition-colors line-clamp-1">
                          {m.question}
                        </span>
                        {m.slug && (
                          <a
                            href={`https://polymarket.com/market/${m.slug}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="text-slate-500 hover:text-emerald-400 transition-colors opacity-60 group-hover:opacity-100"
                            title="Open in Polymarket"
                          >
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                      </div>
                    </td>

                    {/* Status Pill */}
                    <td className="py-2.5 px-3">{statusBadge}</td>

                    {/* Latest Dispute Started */}
                    <td className="py-2.5 px-3 font-mono text-[11px] text-slate-400">
                      {formatUTC(m.latest_dispute_started, true, false)}
                    </td>

                    {/* Market Closed Time */}
                    <td className="py-2.5 px-3 font-mono text-[11px] text-slate-400">
                      {m.market_closed_time ? formatUTC(m.market_closed_time, true, false) : "—"}
                    </td>

                    {/* YES Price */}
                    <td className="py-2.5 px-3 text-right font-mono font-semibold text-emerald-400">
                      ${m.yes_price.toFixed(3)}
                    </td>

                    {/* NO Price */}
                    <td className="py-2.5 px-3 text-right font-mono font-semibold text-rose-400">
                      ${m.no_price.toFixed(3)}
                    </td>

                    {/* Total Voters */}
                    <td className="py-2.5 px-3 text-center font-mono text-slate-300">
                      <span className="rounded bg-slate-800/80 px-2 py-0.5 border border-slate-700 text-[11px]">
                        {m.total_voters}
                      </span>
                    </td>

                    {/* Predominant Vote */}
                    <td className={`py-2.5 px-3 font-mono text-[11px] ${predomColor}`}>
                      {m.predominant_vote}
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
