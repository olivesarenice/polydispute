import React from "react";
import { X, Sliders, ShieldCheck, Scale, RefreshCw, Lock } from "lucide-react";

export default function SettingsModal({ isOpen, onClose, settings, setSettings, defaultSettings }) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="w-full max-w-lg rounded-xl border border-slate-700/80 bg-[#0e1524] shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4 bg-slate-900/60">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-800 text-slate-400 border border-slate-700">
              <Sliders className="h-4 w-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-slate-100">Global System Parameters</h3>
                <span className="inline-flex items-center gap-1 rounded bg-slate-800 text-slate-400 border border-slate-700 px-1.5 py-0.2 text-[10px] font-mono">
                  <Lock className="h-2.5 w-2.5" /> Locked
                </span>
              </div>
              <p className="text-xs text-slate-400">Settings are locked to system-wide default calibration parameters</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="space-y-6 px-6 py-5 max-h-[75vh] overflow-y-auto">
          {/* Section 1: Discord Noise Filter */}
          <div className="rounded-lg border border-slate-800/80 bg-slate-900/40 p-4 space-y-4">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
              <ShieldCheck className="h-4 w-4 text-slate-400" />
              <span>1. Discord Noise Filter</span>
            </div>

            {/* Min Experience */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <span className="text-slate-400 font-medium">Minimum Experience (Votes)</span>
                <span className="font-mono text-slate-300 font-semibold">{settings.minExperienceVotes} votes</span>
              </div>
              <input
                type="range"
                min="3"
                max="100"
                step="1"
                disabled
                value={settings.minExperienceVotes}
                className="w-full accent-slate-500 cursor-not-allowed opacity-40 h-1.5 bg-slate-800 rounded-lg"
              />
              <p className="text-[11px] text-slate-500">
                Excludes voters with fewer than N lifetime historical predictions in the database.
              </p>
            </div>

            {/* Min Competency */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <span className="text-slate-400 font-medium">Minimum Competency (Bayesian Accuracy)</span>
                <span className="font-mono text-slate-300 font-semibold">{settings.minCompetencyPct}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="80"
                step="5"
                disabled
                value={settings.minCompetencyPct}
                className="w-full accent-slate-500 cursor-not-allowed opacity-40 h-1.5 bg-slate-800 rounded-lg"
              />
              <p className="text-[11px] text-slate-500">
                Filters out voters whose smoothed Bayesian accuracy is below X% (greyed out on dot charts).
              </p>
            </div>
          </div>

          {/* Section 2: Bayesian Calibration */}
          <div className="rounded-lg border border-slate-800/80 bg-slate-900/40 p-4 space-y-4">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
              <Scale className="h-4 w-4 text-slate-400" />
              <span>2. Bayesian Accuracy Parameters</span>
            </div>

            {/* Trust Number N */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <span className="text-slate-400 font-medium">Trust Number (N)</span>
                <span className="font-mono text-slate-300 font-semibold">{settings.trustNumber} pseudo-obs</span>
              </div>
              <input
                type="range"
                min="10"
                max="50"
                step="1"
                disabled
                value={settings.trustNumber}
                className="w-full accent-slate-500 cursor-not-allowed opacity-40 h-1.5 bg-slate-800 rounded-lg"
              />
              <p className="text-[11px] text-slate-500">
                Strength of prior belief: Higher values anchor low-volume voters closer to the 50% baseline.
              </p>
            </div>

            {/* Prior Score P */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <span className="text-slate-400 font-medium">Prior Score Baseline</span>
                <span className="font-mono text-slate-300 font-semibold">{Math.round(settings.priorScore * 100)}%</span>
              </div>
              <input
                type="range"
                min="0.2"
                max="0.8"
                step="0.05"
                disabled
                value={settings.priorScore}
                className="w-full accent-slate-500 cursor-not-allowed opacity-40 h-1.5 bg-slate-800 rounded-lg"
              />
              <p className="text-[11px] text-slate-500">
                Default uncalibrated prior probability for forecasters with 0 prior bets.
              </p>
            </div>

            {/* Fixed Weighting Scheme */}
            <div className="flex items-center justify-between rounded-md bg-slate-950/60 p-2.5 border border-slate-800 text-xs">
              <span className="text-slate-400">Power Weighting Scheme</span>
              <span className="rounded bg-slate-800 px-2 py-0.5 font-mono font-semibold text-slate-400 border border-slate-700">
                Quadratic (S²) — Fixed
              </span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-800 px-6 py-3.5 bg-slate-900/60">
          <button
            disabled
            className="flex items-center gap-1.5 text-xs text-slate-600 cursor-not-allowed"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Reset Defaults</span>
          </button>

          <button
            disabled
            className="rounded-lg bg-slate-800/90 px-4 py-1.5 text-xs font-semibold text-slate-500 border border-slate-700/60 cursor-not-allowed shadow-sm"
          >
            Configuration Disabled
          </button>
        </div>
      </div>
    </div>
  );
}
