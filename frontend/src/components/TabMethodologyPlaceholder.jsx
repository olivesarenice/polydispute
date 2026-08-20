import React from "react";
import { BookOpen, CheckCircle, ShieldCheck, Cpu } from "lucide-react";

export default function TabMethodologyPlaceholder() {
  return (
    <div className="w-full max-w-7xl mx-auto space-y-6 py-4 animate-in fade-in duration-200">
      {/* Header */}
      <div className="rounded-xl border border-slate-800 bg-[#0e1524] p-5 shadow-lg">
        <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
          <BookOpen className="h-5 w-5 text-emerald-400" />
          <span>Polydispute Alpha Thesis & Mathematical Framework</span>
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          Detailed documentation of Empirical Bayes voter scoring, Option 2 payoff mechanics, and historical validation backtests.
        </p>
      </div>

      {/* Key Formulas Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl border border-slate-800 bg-[#0e1524] p-4 space-y-2">
          <div className="flex items-center gap-2 text-xs font-bold text-emerald-400">
            <Cpu className="h-4 w-4" />
            <span>1. Bayesian Calibration (S)</span>
          </div>
          <div className="rounded bg-slate-950 p-2.5 font-mono text-xs text-slate-300 border border-slate-800">
            S = (P * N + C) / (N + G)
          </div>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            Smoothes voter accuracy by blending historical wins C over gradeable disputes G with prior baseline P=50% across N pseudo-observations.
          </p>
        </div>

        <div className="rounded-xl border border-slate-800 bg-[#0e1524] p-4 space-y-2">
          <div className="flex items-center gap-2 text-xs font-bold text-cyan-400">
            <Scale className="h-4 w-4" />
            <span>2. Power Weighting (W)</span>
          </div>
          <div className="rounded bg-slate-950 p-2.5 font-mono text-xs text-slate-300 border border-slate-800">
            W = (S)²
          </div>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            Quadratic power amplification exponentially suppresses uncalibrated noise while magnifying 80%+ verified expert forecasters.
          </p>
        </div>

        <div className="rounded-xl border border-slate-800 bg-[#0e1524] p-4 space-y-2">
          <div className="flex items-center gap-2 text-xs font-bold text-purple-400">
            <ShieldCheck className="h-4 w-4" />
            <span>3. Option 2 Payoff Vector</span>
          </div>
          <div className="rounded bg-slate-950 p-2.5 font-mono text-xs text-slate-300 border border-slate-800">
            P4 Payoff = P_market(t_vote)
          </div>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            P1 pays $0.00, P2 pays $1.00, P3 pays $0.50, and P4 (Too Early) anchors each vote to the point-in-time observed market YES price.
          </p>
        </div>
      </div>
    </div>
  );
}

function Scale(props) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
      <path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
      <path d="M7 21h10" />
      <path d="M12 3v18" />
      <path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2" />
    </svg>
  );
}
