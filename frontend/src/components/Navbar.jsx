import React from "react";
import { Settings, BarChart3, Users, BookOpen } from "lucide-react";

export default function Navbar({ activeTab, setActiveTab, onOpenSettings, liveDisputesCount }) {
  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-800/80 bg-[#080c14]/90 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
        {/* Left: Brand / Logo + Tab Navigation aligned together */}
        <div className="flex items-center gap-6 sm:gap-8">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-800/80 border border-slate-700 text-slate-200 font-bold text-base shadow-sm">
              ⚖
            </div>
            <span className="font-mono text-base font-bold tracking-wider text-slate-100">
              POLY<span className="text-slate-400">DISPUTE</span>
            </span>
          </div>

          {/* Tab Navigation (Unboxed) */}
          <nav className="flex items-center gap-1">
            <button
              onClick={() => setActiveTab("dashboard")}
              className={`flex items-center gap-1.5 sm:gap-2 rounded-md px-2.5 sm:px-3 py-1.5 text-xs font-medium transition-all ${
                activeTab === "dashboard"
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
              className={`flex items-center gap-1.5 sm:gap-2 rounded-md px-2.5 sm:px-3 py-1.5 text-xs font-medium transition-all ${
                activeTab === "leaderboard"
                  ? "bg-slate-800 text-slate-100 border border-slate-600 shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
              }`}
            >
              <Users className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Voter Calibration</span>
              <span className="sm:hidden">Voters</span>
            </button>

            <button
              onClick={() => setActiveTab("methodology")}
              className={`flex items-center gap-1.5 sm:gap-2 rounded-md px-2.5 sm:px-3 py-1.5 text-xs font-medium transition-all ${
                activeTab === "methodology"
                  ? "bg-slate-800 text-slate-100 border border-slate-600 shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
              }`}
            >
              <BookOpen className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Methodology</span>
              <span className="sm:hidden">Docs</span>
            </button>
          </nav>
        </div>

        {/* Right side: Settings Gear */}
        <div className="flex items-center gap-2">
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
