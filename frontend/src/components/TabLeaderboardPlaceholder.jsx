import React from "react";
import { Users, Trophy, Award, Search, Sliders } from "lucide-react";

export default function TabLeaderboardPlaceholder({ minCompetencyPct }) {
  return (
    <div className="w-full max-w-7xl mx-auto space-y-6 py-4 animate-in fade-in duration-200">
      {/* Header */}
      <div className="rounded-xl border border-slate-800 bg-[#0e1524] p-5 shadow-lg flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Trophy className="h-5 w-5 text-amber-400" />
            <span>Voter Calibration & Accuracy Leaderboard</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Empirical Bayes calibration rankings for 760+ forecasters participating in Polymarket UMA DVM disputes.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="rounded-md bg-emerald-500/10 px-3 py-1 text-xs font-mono text-emerald-400 border border-emerald-500/30">
            Current Filter: ≥{minCompetencyPct}% Bayesian Accuracy
          </span>
        </div>
      </div>

      {/* Cohort Distribution Placeholder Card */}
      <div className="rounded-xl border border-slate-800 bg-[#0e1524] p-6 text-center space-y-3">
        <Users className="h-10 w-10 text-emerald-400 mx-auto opacity-70" />
        <h3 className="text-base font-semibold text-slate-200">Full Leaderboard Analytics Module</h3>
        <p className="text-xs text-slate-400 max-w-lg mx-auto">
          The full voter calibration suite (cohort histograms, exclusion zone shading, and per-voter track records) is in development.
        </p>
      </div>
    </div>
  );
}
