import { Activity, BarChart3, BookOpen, Clock, Database, Layers, Settings, Users } from "lucide-react";
import { useState } from "react";
import ThemisScalesLogo from "./ThemisScalesLogo";
import { formatRelativeTime, formatUTC } from "./ScreenerTable";

export default function Navbar({
  activeTab,
  setActiveTab,
  onOpenSettings,
  liveDisputesCount,
  health,
  healthLoading,
  onRetryHealth,
}) {
  const [showHealthTooltip, setShowHealthTooltip] = useState(false);

  const isOnline = health?.status === "ok" && health?.database === "connected";
  const isConnecting = healthLoading && !health;

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-800/80 bg-[#080c14]/90 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
        {/* Left: Brand / Logo + Tab Navigation aligned together */}
        <div className="flex items-center gap-6 sm:gap-8">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900/90 border border-slate-700/80 shadow-sm">
              <ThemisScalesLogo className="h-5 w-5" />
            </div>
            <span className="font-mono text-base font-bold tracking-wider text-slate-100">
              POLY<span className="text-slate-400">DISPUTE</span>
            </span>
          </div>

          {/* Tab Navigation */}
          <nav className="flex items-center gap-1">
            <button
              onClick={() => setActiveTab("dashboard")}
              className={`flex items-center gap-1.5 sm:gap-2 rounded-md px-2.5 sm:px-3 py-1.5 text-xs font-medium transition-all ${activeTab === "dashboard"
                  ? "bg-slate-800 text-slate-100 border border-slate-600 shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
                }`}
            >
              <BarChart3 className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Screener & Analysis</span>
              <span className="sm:hidden">Screener</span>
              {liveDisputesCount > 0 && (
                <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-cyan-500/20 px-1 text-[10px] font-bold text-cyan-300 border border-cyan-500/40 live-pulse-glow">
                  {liveDisputesCount}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("leaderboard")}
              className={`flex items-center gap-1.5 sm:gap-2 rounded-md px-2.5 sm:px-3 py-1.5 text-xs font-medium transition-all ${activeTab === "leaderboard"
                  ? "bg-slate-800 text-slate-100 border border-slate-600 shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
                }`}
            >
              <Users className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Voter Calibration</span>
              <span className="sm:hidden">Voters</span>
            </button>

            {/* Feature-flagged off for now */}
            {false && (
              <button
                onClick={() => setActiveTab("methodology")}
                className={`flex items-center gap-1.5 sm:gap-2 rounded-md px-2.5 sm:px-3 py-1.5 text-xs font-medium transition-all ${activeTab === "methodology"
                    ? "bg-slate-800 text-slate-100 border border-slate-600 shadow-sm"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
                  }`}
              >
                <BookOpen className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Methodology</span>
                <span className="sm:hidden">Docs</span>
              </button>
            )}
          </nav>
        </div>

        {/* Right side: Site Status Pill & Settings Gear */}
        <div className="flex items-center gap-3">
          {/* Site Status Pill with Hover Diagnostic Tooltip */}
          <div
            className="relative"
            onMouseEnter={() => setShowHealthTooltip(true)}
            onMouseLeave={() => setShowHealthTooltip(false)}
          >
            <button
              onClick={onRetryHealth}
              className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-mono font-medium border transition-all cursor-pointer ${isOnline
                  ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/20"
                  : isConnecting
                    ? "bg-amber-500/10 text-amber-300 border-amber-500/30 hover:bg-amber-500/20 animate-pulse"
                    : "bg-rose-500/10 text-rose-300 border-rose-500/30 hover:bg-rose-500/20"
                }`}
              title="Click to check backend connection"
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${isOnline
                    ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]"
                    : isConnecting
                      ? "bg-amber-400 animate-ping"
                      : "bg-rose-400 shadow-[0_0_8px_rgba(251,113,133,0.8)]"
                  }`}
              />
              <span>{isOnline ? "ONLINE" : isConnecting ? "CONNECTING" : "OFFLINE"}</span>
            </button>

            {/* Hover Tooltip Popup */}
            {showHealthTooltip && (
              <div className="absolute right-0 top-9 z-50 w-72 rounded-xl border border-slate-700 bg-slate-900/95 p-3.5 text-xs text-slate-300 shadow-2xl backdrop-blur-md pointer-events-none animate-in fade-in slide-in-from-top-1 duration-150">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-2.5">
                  <div className="flex items-center gap-1.5 font-semibold text-slate-100 font-sans">
                    <Activity className="h-3.5 w-3.5 text-cyan-400" />
                    <span>System Health & Telemetry</span>
                  </div>
                  <span
                    className={`rounded px-1.5 py-0.2 font-mono text-[10px] font-bold ${isOnline ? "bg-emerald-500/20 text-emerald-300" : "bg-rose-500/20 text-rose-300"
                      }`}
                  >
                    {isOnline ? "ONLINE" : "DISCONNECTED"}
                  </span>
                </div>

                <div className="space-y-2 font-mono text-[11px]">
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-slate-400">
                      <Database className="h-3 w-3 text-slate-500" />
                      <span>Target DB:</span>
                    </span>
                    <span className="text-cyan-300 font-semibold">
                      {health?.database_target || "md:polydispute_dev"}
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-slate-400">
                      <Activity className="h-3 w-3 text-slate-500" />
                      <span>Ping Latency:</span>
                    </span>
                    <span className="text-slate-200">
                      {health?.motherduck_latency_ms != null
                        ? `${health.motherduck_latency_ms} ms`
                        : "—"}
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-slate-400">
                      <Layers className="h-3 w-3 text-slate-500" />
                      <span>Cached Markets:</span>
                    </span>
                    <span className="text-slate-200">
                      {health?.cached_markets_count != null
                        ? `${health.cached_markets_count} in memory`
                        : "—"}
                    </span>
                  </div>

                  <div className="flex items-center justify-between border-t border-slate-800/80 pt-1.5 mt-1.5">
                    <span className="flex items-center gap-1.5 text-slate-400">
                      <Clock className="h-3 w-3 text-slate-500" />
                      <span>Last Refresh:</span>
                    </span>
                    <span className="text-slate-300 text-right">
                      {health?.timestamp ? (
                        <>
                          <span className="text-cyan-400 font-medium">
                            {formatRelativeTime(health.timestamp)}
                          </span>{" "}
                          <span className="text-[10px] text-slate-500 block">
                            {formatUTC(health.timestamp, true, false)}
                          </span>
                        </>
                      ) : (
                        "Never"
                      )}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Settings Modal Button */}
          <button
            onClick={onOpenSettings}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-700/80 bg-slate-900 text-slate-300 hover:border-slate-500 hover:text-white transition-colors"
            title="Global Settings"
          >
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
