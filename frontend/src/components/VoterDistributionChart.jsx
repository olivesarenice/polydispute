import React from "react";

export default function VoterDistributionChart({
  voterDistribution,
  cohortRms,
  cohortCounts,
  consensusTrajectory,
  minCompetencyPct = 50,
  selectedVoterUsername,
  onSelectVoter,
}) {
  const allLanes = [
    { key: "P2", label: "YES", color: "#10b981", badgeBg: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40", barBg: "bg-emerald-500/25" },
    { key: "P1", label: "NO", color: "#f43f5e", badgeBg: "bg-rose-500/15 text-rose-300 border-rose-500/40", barBg: "bg-rose-500/25" },
    { key: "P3", label: "UNKNOWN", color: "#f59e0b", badgeBg: "bg-amber-500/15 text-amber-300 border-amber-500/40", barBg: "bg-amber-500/25" },
    { key: "P4", label: "EARLY", color: "#a855f7", badgeBg: "bg-purple-500/15 text-purple-300 border-purple-500/40", barBg: "bg-purple-500/25" },
  ];

  const latestRec = consensusTrajectory && consensusTrajectory.length > 0
    ? consensusTrajectory[consensusTrajectory.length - 1]
    : null;

  const getSharePct = (laneKey) => {
    if (!latestRec) return 0;
    if (laneKey === "P1") return latestRec.p1_weighted_pct || 0;
    if (laneKey === "P2") return latestRec.p2_weighted_pct || 0;
    if (laneKey === "P3") return latestRec.p3_weighted_pct || 0;
    if (laneKey === "P4") return latestRec.p4_weighted_pct || 0;
    return 0;
  };

  // Only display lanes that have votes or consensus share
  const activeLanes = allLanes.filter(
    (lane) => (cohortCounts[lane.key] || 0) > 0 || getSharePct(lane.key) > 0
  );

  return (
    <div className="w-full rounded-xl border border-slate-800 bg-[#0e1524] p-4 shadow-md space-y-3">
      {/* Chart Title Header & Legend */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-2">
        <h4 className="text-xs font-bold text-slate-200">
          Voter Accuracy Distribution
        </h4>
        {/* Legend */}
        <div className="flex flex-wrap items-center gap-2 sm:gap-3 text-[9px] sm:text-[9.5px] text-slate-400 font-sans">
          <div className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-3.5 rounded-xs bg-slate-400/40 border border-slate-400/60" />
            <span>Weighted Consensus Share</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full bg-slate-300 border border-slate-900" />
            <span>Voter's Past Accuracy</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-[2px] bg-white shadow-xs" />
            <span>Avg. Voter Accuracy</span>
          </div>
        </div>
      </div>

      {activeLanes.length === 0 ? (
        <div className="py-6 text-center text-xs text-slate-500 font-mono">
          No votes recorded for this dispute round.
        </div>
      ) : (
        <div className="space-y-1.5">
          {/* Unified X-Axis Header (0% to 100%) */}
          <div className="flex items-center gap-2">
            {/* Empty space matching left label column */}
            <div className="w-24 sm:w-28 shrink-0" />
            {/* Shared Track X-Axis Scale */}
            <div className="relative flex-1 h-3 text-[9px] font-mono text-slate-500 flex justify-between select-none px-0.5">
              <span>0%</span>
              <span>25%</span>
              <span>50%</span>
              <span>75%</span>
              <span>100%</span>
            </div>
          </div>

          {/* Unified Chart Canvas Container */}
          <div className="relative rounded border border-slate-800/90 bg-[#0a0f1d] p-1.5 space-y-1.5 overflow-hidden">
            {/* Stacked Active Outcome Rows */}
            {activeLanes.map((lane) => {
              const sharePct = getSharePct(lane.key);
              const rmsVal = cohortRms[lane.key] || 0;
              const countVal = cohortCounts[lane.key] || 0;
              const laneVoters = (voterDistribution || []).filter((v) => v.vote_type === lane.key);

              return (
                <div key={lane.key} className="flex items-center gap-2">
                  {/* Left Outcome Stance Label & Stats */}
                  <div className="w-24 sm:w-28 shrink-0 flex items-center gap-1 sm:gap-1.5">
                    <span className={`rounded px-1.5 py-0.5 font-mono text-[9px] sm:text-[9.5px] font-bold border ${lane.badgeBg}`}>
                      {lane.label}
                    </span>
                    <span className="text-[9px] sm:text-[9.5px] text-slate-400 font-mono whitespace-nowrap">
                      {countVal} {countVal === 1 ? "vote" : "votes"}
                    </span>
                  </div>

                  {/* Single Track Bar */}
                  <div className="relative flex-1 h-7 rounded bg-slate-950/90 border border-slate-800/80 overflow-hidden flex items-center">
                    {/* Background Consensus Share Bar */}
                    <div
                      className={`absolute top-0 bottom-0 left-0 ${lane.barBg} transition-all duration-300`}
                      style={{ width: `${Math.min(100, Math.max(0, sharePct))}%` }}
                    />

                    {/* Share % Label on Left Inside the Bar (Rounded to Integer) */}
                    <span className="absolute left-2 z-10 text-[10px] font-mono font-bold text-slate-100 select-none pointer-events-none drop-shadow">
                      {Math.round(sharePct)}%
                    </span>

                    {/* Cutoff Dotted Line */}
                    <div
                      className="absolute top-0 bottom-0 border-r border-dashed border-rose-500/60 z-10 pointer-events-none"
                      style={{ left: `${minCompetencyPct}%` }}
                    />

                    {/* Voter Dots along the Track */}
                    {laneVoters.map((v, vIdx) => {
                      const isExcluded = v.bayesian_accuracy_pct < minCompetencyPct;
                      const isSelected = selectedVoterUsername && v.author_username && v.author_username.toLowerCase() === selectedVoterUsername.toLowerCase();
                      const verticalOffset = ((vIdx % 3) - 1) * 3.5;

                      return (
                        <div
                          key={vIdx}
                          onClick={() => onSelectVoter && onSelectVoter(v)}
                          className={`absolute cursor-pointer transition-all ${isSelected ? "z-30" : "z-10"}`}
                          style={{
                            left: `calc(${Math.min(97, Math.max(3, v.bayesian_accuracy_pct))}% - 5px)`,
                            top: `calc(50% + ${verticalOffset}px - 5px)`,
                          }}
                          title={`@${v.author_username}: ${Math.round(v.bayesian_accuracy_pct)}% Accuracy ${isExcluded ? "(Excluded)" : "(Qualified)"} · Click to view reasoning in feed`}
                        >
                          <div
                            className={`h-2.5 w-2.5 rounded-full border shadow-sm transition-all duration-150 ${
                              isSelected
                                ? "ring-2 ring-white scale-140 shadow-lg border-white"
                                : "hover:scale-150 border-slate-900 shadow-md"
                            } ${
                              isExcluded
                                ? "bg-slate-600 border-slate-500 opacity-50"
                                : ""
                            }`}
                            style={{
                              backgroundColor: isExcluded ? undefined : lane.color,
                            }}
                          />
                        </div>
                      );
                    })}

                    {/* Cohort Average Marker (Solid White Line with Bottom-Right White Callout Text) */}
                    {countVal > 0 && rmsVal > 0 && (
                      <div
                        className="absolute top-0 bottom-0 z-20 pointer-events-none"
                        style={{ left: `${Math.min(96, Math.max(4, rmsVal))}%` }}
                        title={`Avg. Accuracy: ${Math.round(rmsVal)}%`}
                      >
                        {/* Solid White Line */}
                        <div className="absolute top-0 bottom-0 -left-[1px] w-[2px] bg-white shadow-md" />
                        {/* Bottom Right White Text without background */}
                        <span className="absolute bottom-0.5 left-1 text-white font-mono text-[8.5px] font-bold leading-none select-none drop-shadow-[0_1px_2px_rgba(0,0,0,0.9)]">
                          {Math.round(rmsVal)}%
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
