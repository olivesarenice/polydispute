import {
  ArrowDown,
  ArrowUp,
  Loader2,
  Search,
  ShieldCheck,
  Trophy
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchLeaderboard } from "../lib/api";

function formatDDMmmYY(dateStr) {
  if (!dateStr) return "";
  const parts = dateStr.split("-");
  if (parts.length !== 3) return dateStr;
  const year = parts[0].slice(2);
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  const mIdx = parseInt(parts[1], 10) - 1;
  return `${parts[2]} ${months[mIdx] || parts[1]} ${year}`;
}

function CustomWeeklyTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const data = payload[0]?.payload;
  if (!data) return null;

  return (
    <div className="rounded-lg border border-slate-700 bg-[#0b101c]/95 p-2.5 shadow-xl text-xs font-mono space-y-1 min-w-[170px]">
      <div className="font-bold text-slate-200 border-b border-slate-800 pb-1">
        {data.week_start}
      </div>
      <div className="flex items-center justify-between gap-3 text-slate-400">
        <span>Disputed Markets:</span>
        <span className="font-bold text-slate-200">{data.disputed_markets_count}</span>
      </div>
      <div className="flex items-center justify-between gap-3 text-slate-400">
        <span>Accuracy:</span>
        <span className="font-bold text-white">
          {data.accuracy_pct != null ? `${data.accuracy_pct.toFixed(1)}%` : "N/A"}
        </span>
      </div>
    </div>
  );
}

export default function TabLeaderboardPlaceholder({ minCompetencyPct = 50, minPredictions = 10 }) {
  const [voters, setVoters] = useState([]);
  const [groupAccuracy, setGroupAccuracy] = useState(null);
  const [thresholdConfig, setThresholdConfig] = useState({
    minCompetencyPct: minCompetencyPct ?? 50,
    minPredictions: minPredictions ?? 10,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("bayesian_accuracy_pct");
  const [sortDir, setSortDir] = useState("desc");

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    fetchLeaderboard({ minCompetencyPct, minPredictions, limit: 1000 })
      .then((data) => {
        if (isMounted) {
          setVoters(data.voters || []);
          setGroupAccuracy(data.group_accuracy || null);
          setThresholdConfig({
            minCompetencyPct: data.min_competency_pct ?? minCompetencyPct ?? 50,
            minPredictions: data.min_predictions ?? minPredictions ?? 10,
          });
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err.message);
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [minCompetencyPct, minPredictions]);

  const qualifiedCount = useMemo(
    () => voters.filter((v) => v.is_calibrated).length,
    [voters]
  );

  const filteredVoters = useMemo(() => {
    return voters
      .filter((v) => {
        if (!search.trim()) return true;
        return v.author_username.toLowerCase().includes(search.toLowerCase());
      })
      .sort((a, b) => {
        const valA = a[sortBy];
        const valB = b[sortBy];
        if (typeof valA === "number" && typeof valB === "number") {
          return sortDir === "asc" ? valA - valB : valB - valA;
        }
        return sortDir === "asc"
          ? String(valA).localeCompare(String(valB))
          : String(valB).localeCompare(String(valA));
      });
  }, [voters, search, sortBy, sortDir]);

  const handleSort = (field) => {
    if (sortBy === field) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortBy(field);
      setSortDir("desc");
    }
  };

  const qual = groupAccuracy?.qualified;

  return (
    <div className="w-full max-w-7xl mx-auto space-y-4 py-2">
      {/* Unified Voter Calibration & Discord Group Stats Panel */}
      <div className="rounded-xl border border-slate-800 bg-[#0e1524] p-5 shadow-lg space-y-4">
        {/* Header Row & Headliner KPIs */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="space-y-1">
            <h2 className="text-base sm:text-lg font-bold text-slate-100 flex items-center gap-2 font-sans">
              <Trophy className="h-5 w-5 text-amber-400" />
              <span>Voter Calibration & Accuracy Leaderboard</span>
            </h2>
            <p className="text-xs text-slate-400 font-sans">
              Bayesian calibration for Discord users commenting on Polymarket disputes.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-6 sm:gap-8">
            {/* KPI 1: Qualification Threshold */}
            <div className="space-y-1">
              <div className="h-4 flex items-center text-[11px] text-slate-400 font-medium font-sans">
                Qualification Threshold
              </div>
              <div className="h-6 flex items-center gap-1.5 font-mono">
                <span className="text-sm font-bold text-emerald-400 leading-none">
                  ≥{thresholdConfig.minCompetencyPct % 1 === 0 ? thresholdConfig.minCompetencyPct : Number(thresholdConfig.minCompetencyPct).toFixed(1)}%
                </span>
                <span className="text-xs text-emerald-500/90 font-medium leading-none">
                  Bayesian
                </span>
                <span className="text-slate-600 text-xs font-normal leading-none mx-0.5">·</span>
                <span className="text-sm font-bold text-slate-200 leading-none">
                  ≥{thresholdConfig.minPredictions}
                </span>
                <span className="text-xs text-slate-400 font-medium leading-none">
                  Votes
                </span>
              </div>
            </div>

            {/* KPI 2: Qualified Discord Users */}
            <div className="space-y-1">
              <div className="h-4 flex items-center text-[11px] text-slate-400 font-medium font-sans">
                Qualified Discord Users
              </div>
              <div className="h-6 flex items-center gap-1.5 font-mono">
                <span className="text-sm font-bold text-slate-100 leading-none">
                  {qualifiedCount}
                </span>
                <span className="text-xs text-slate-500 leading-none">/</span>
                <span className="text-xs text-slate-400 leading-none">
                  {voters.length} Discord Users
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Discord Group Stats Section */}
        {groupAccuracy && (
          <div className="pt-4 border-t border-slate-800/80 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-slate-200 font-sans">
                Discord Group Stats
              </h3>
            </div>

            {/* 2-Column Layout: Left = Qualified Accuracy Card (4 cols), Right = Weekly Breakdown (8 cols) */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 sm:gap-5">
              {/* Left Column: Qualified Discord User Accuracy */}
              <div className="lg:col-span-4 rounded-xl border border-slate-800 bg-[#0d1322] p-4 sm:p-5 flex flex-col justify-between">
                <div className="space-y-1">
                  <div className="text-[11px] text-slate-400 font-medium font-sans">
                    Qualified Discord User Accuracy
                  </div>
                  <p className="text-xs text-slate-400 font-sans leading-relaxed">
                    # of markets where Discord consensus matches resolved UMA vote*
                  </p>
                </div>

                <div className="my-auto py-4">
                  <div className="flex items-baseline gap-2.5 font-mono">
                    <span className="text-4xl sm:text-5xl font-bold text-emerald-400 leading-none">
                      {qual?.accuracy_pct != null ? `${qual.accuracy_pct.toFixed(1)}%` : "N/A"}
                    </span>
                    <span className="text-xs text-slate-400 font-mono leading-none">
                      ({qual?.correct_markets ?? 0} / {qual?.consensus_markets ?? 0} markets)
                    </span>
                  </div>
                </div>

                <div className="text-[10px] font-mono text-slate-500">
                  *Excludes P4 - Too Early
                </div>
              </div>

              {/* Right Column: Weekly Breakdown Panel */}
              <div className="lg:col-span-8 rounded-xl border border-slate-800 bg-[#090e18] p-4 flex flex-col justify-between shadow-inner">
                {/* Panel Header & Legend */}
                <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                  <div className="text-[11px] text-slate-400 font-medium font-sans">
                    Weekly Accuracy
                  </div>

                  {/* Legend Indicators */}
                  <div className="flex items-center gap-3.5 text-[11px] font-sans">
                    <div className="flex items-center gap-1.5">
                      <span className="inline-block h-2.5 w-2.5 rounded-xs bg-[#475569]" />
                      <span className="text-slate-400 font-sans">Disputed Markets</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="inline-block h-[1px] w-3.5 bg-white" />
                      <span className="text-slate-300 font-sans">Accuracy</span>
                    </div>
                  </div>
                </div>

                {/* Chart */}
                <div className="h-[210px] w-full mt-1">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart
                      data={groupAccuracy.weekly_breakdown || []}
                      margin={{ top: 8, right: 8, left: -24, bottom: 6 }}
                    >
                      <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} />
                      <XAxis
                        dataKey="week_start"
                        tickFormatter={formatDDMmmYY}
                        tick={{ fill: "#94a3b8", fontSize: 10, fontFamily: "monospace" }}
                        tickLine={{ stroke: "#64748b", strokeWidth: 1 }}
                        tickMargin={6}
                        axisLine={{ stroke: "#475569" }}
                        minTickGap={24}
                      />
                      <YAxis
                        yAxisId="left"
                        orientation="left"
                        allowDecimals={false}
                        tick={{ fill: "#64748b", fontSize: 10, fontFamily: "monospace" }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <YAxis
                        yAxisId="right"
                        orientation="right"
                        domain={[0, 100]}
                        ticks={[0, 25, 50, 75, 100]}
                        tickFormatter={(v) => `${v}%`}
                        tick={{ fill: "#94a3b8", fontSize: 10, fontFamily: "monospace" }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <Tooltip content={<CustomWeeklyTooltip />} />
                      <Bar
                        yAxisId="left"
                        dataKey="disputed_markets_count"
                        name="Disputed Markets"
                        fill="#475569"
                        radius={[2, 2, 0, 0]}
                        maxBarSize={18}
                        isAnimationActive={false}
                      />
                      <Line
                        yAxisId="right"
                        type="linear"
                        dataKey="accuracy_pct"
                        name="Accuracy"
                        stroke="#ffffff"
                        strokeWidth={1}
                        dot={{ r: 1.5, fill: "#ffffff" }}
                        activeDot={{ r: 3.5, fill: "#ffffff" }}
                        connectNulls={true}
                        isAnimationActive={false}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Control & Search Bar */}
      <div className="flex items-center justify-between gap-4">
        <div className="relative min-w-[260px] max-w-xs">
          <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search Discord users..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-slate-800 bg-[#0d1322] pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 transition-all font-sans"
          />
        </div>
      </div>

      {/* Table Content */}
      {loading ? (
        <div className="rounded-xl border border-slate-800 bg-[#0d1322] p-12 text-center text-slate-400 space-y-3">
          <div className="relative mx-auto flex h-10 w-10 items-center justify-center">
            <Loader2 className="h-7 w-7 animate-spin text-cyan-400" />
          </div>
          <p className="text-xs font-mono">Loading Discord user calibration profiles from MotherDuck...</p>
        </div>
      ) : error ? (
        <div className="rounded-xl border border-rose-800/50 bg-rose-950/20 p-6 text-center text-rose-300 text-xs font-mono">
          Failed to load leaderboard: {error}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-800 bg-[#0d1322] shadow-xl">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="border-b border-slate-800 bg-slate-900/60 font-mono text-[11px] uppercase tracking-wider text-slate-400">
              <tr>
                <th className="py-2.5 px-4 text-center w-16">Rank</th>
                <th
                  onClick={() => handleSort("author_username")}
                  className="py-2.5 px-4 cursor-pointer hover:text-slate-200 transition-colors"
                >
                  Discord User
                </th>
                <th
                  onClick={() => handleSort("bayesian_accuracy_pct")}
                  className="py-2.5 px-4 cursor-pointer hover:text-slate-200 transition-colors text-right"
                >
                  <div className="flex items-center justify-end gap-1">
                    <span className="text-emerald-400 font-semibold">Bayesian Score (S)</span>
                    {sortBy === "bayesian_accuracy_pct" && (
                      sortDir === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />
                    )}
                  </div>
                </th>
                <th
                  onClick={() => handleSort("lifetime_accuracy_pct")}
                  className="py-2.5 px-4 cursor-pointer hover:text-slate-200 transition-colors text-right"
                >
                  <div className="flex items-center justify-end gap-1">
                    <span>Raw Win Rate</span>
                    {sortBy === "lifetime_accuracy_pct" && (
                      sortDir === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />
                    )}
                  </div>
                </th>
                <th
                  onClick={() => handleSort("correct_predictions")}
                  className="py-2.5 px-4 cursor-pointer hover:text-slate-200 transition-colors text-center"
                >
                  Correct / Graded
                </th>
                <th className="py-2.5 px-4 text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-sans">
              {filteredVoters.length === 0 ? (
                <tr>
                  <td colSpan="6" className="py-10 text-center text-slate-500">
                    No Discord users match the search criteria.
                  </td>
                </tr>
              ) : (
                filteredVoters.map((v) => (
                  <tr key={v.author_username} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 text-center font-mono text-slate-400">
                      {v.rank <= 3 ? (
                        <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-amber-400/20 text-amber-300 text-[10px] font-bold border border-amber-400/40">
                          {v.rank}
                        </span>
                      ) : (
                        `#${v.rank}`
                      )}
                    </td>
                    <td className="py-3 px-4 font-mono font-semibold text-slate-100">
                      {v.author_username}
                    </td>
                    <td className={`py-3 px-4 text-right font-mono text-sm ${v.is_calibrated ? "text-emerald-400 font-bold" : "text-slate-400 font-medium"
                      }`}>
                      {v.bayesian_accuracy_pct.toFixed(1)}%
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-slate-300">
                      {v.lifetime_accuracy_pct.toFixed(1)}%
                    </td>
                    <td className="py-3 px-4 text-center font-mono text-slate-400">
                      <span className="text-slate-200 font-semibold">{v.correct_predictions}</span> / {v.gradeable_predictions}
                    </td>
                    <td className="py-3 px-4 text-center">
                      {v.is_calibrated ? (
                        <span className="inline-flex items-center gap-1 rounded-md bg-cyan-500/15 px-2 py-0.5 font-mono text-[10px] font-medium text-cyan-300 border border-cyan-500/30">
                          <ShieldCheck className="h-3 w-3" />
                          Calibrated
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-md bg-slate-800 px-2 py-0.5 font-mono text-[10px] text-slate-400 border border-slate-700">
                          Uncalibrated
                        </span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
