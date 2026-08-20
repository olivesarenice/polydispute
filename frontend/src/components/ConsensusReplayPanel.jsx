import React, { useState, useRef, useEffect, useMemo } from "react";
import { 
  ResponsiveContainer, 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  Tooltip, 
  CartesianGrid,
  ReferenceLine
} from "recharts";
import { MessageSquare, ExternalLink, ChevronDown, ChevronUp } from "lucide-react";
import VoterDistributionChart from "./VoterDistributionChart";
import MarkdownRenderer from "./MarkdownRenderer";
import { formatUTC } from "./ScreenerTable";

export default function ConsensusReplayPanel({
  consensusTrajectory,
  priceHistory,
  chatMessages,
  voterDistribution,
  cohortRms,
  cohortCounts,
  minCompetencyPct,
}) {
  const [selectedVoterUsername, setSelectedVoterUsername] = useState(null);
  const [activeMessageId, setActiveMessageId] = useState(null);
  const [expandedMessageIds, setExpandedMessageIds] = useState(new Set());
  const [selectedStanceFilter, setSelectedStanceFilter] = useState("ALL");
  const chatContainerRef = useRef(null);
  const messageRefs = useRef({});

  // Prepare unified chart data (merging price history and consensus events on 0-100 scale)
  const { chartData, xTicks, dateTickMap } = useMemo(() => {
    if ((!consensusTrajectory || consensusTrajectory.length === 0) && (!priceHistory || priceHistory.length === 0)) {
      return { chartData: [], xTicks: [], dateTickMap: {} };
    }

    // 1. Determine dispute window boundaries
    let minTimeMs = Infinity;
    let maxTimeMs = -Infinity;

    if (consensusTrajectory && consensusTrajectory.length > 0) {
      consensusTrajectory.forEach((c) => {
        const t = new Date(c.timestamp).getTime();
        if (!isNaN(t)) {
          if (t < minTimeMs) minTimeMs = t;
          if (t > maxTimeMs) maxTimeMs = t;
        }
      });
    }

    if (minTimeMs === Infinity && priceHistory && priceHistory.length > 0) {
      const p0 = new Date(priceHistory[0].timestamp).getTime();
      const pN = new Date(priceHistory[priceHistory.length - 1].timestamp).getTime();
      minTimeMs = p0;
      maxTimeMs = pN;
    }

    const padMs = 2 * 60 * 60 * 1000; // 2 hours padding before & after
    const windowStart = minTimeMs - padMs;
    const windowEnd = maxTimeMs + padMs;

    // 2. Filter price history to the active window
    const windowPrices = (priceHistory || []).filter((p) => {
      const t = new Date(p.timestamp).getTime();
      return !isNaN(t) && t >= windowStart && t <= windowEnd;
    });

    const activePrices = windowPrices.length > 3 ? windowPrices : (priceHistory || []);

    // 3. Collect and merge timeline events
    const timelineEvents = [];

    activePrices.forEach((p) => {
      const t = new Date(p.timestamp).getTime();
      if (!isNaN(t)) {
        timelineEvents.push({
          timeMs: t,
          timestamp: p.timestamp,
          type: "PRICE",
          price: p.yes_price,
        });
      }
    });

    (consensusTrajectory || []).forEach((c) => {
      const t = new Date(c.timestamp).getTime();
      if (!isNaN(t)) {
        timelineEvents.push({
          timeMs: t,
          timestamp: c.timestamp,
          type: "VOTE",
          vote: c,
          price: c.yes_price !== undefined ? c.yes_price : null,
        });
      }
    });

    // 4. Sort chronologically
    timelineEvents.sort((a, b) => a.timeMs - b.timeMs);

    // 5. Forward-fill state accumulator
    let currentPrice = activePrices.length > 0 ? activePrices[0].yes_price : 0.50;
    let currentP1 = null;
    let currentP2 = null;
    let currentP3 = null;
    let currentP4 = null;
    let currentAuthor = null;
    let currentVoteType = null;
    let totalVotesSeen = 0;

    const mergedPoints = [];
    const seenTimes = new Set();
    const seenDates = new Set();
    const midnights = [];
    const tickMap = {};

    timelineEvents.forEach((ev) => {
      if (ev.type === "PRICE" && ev.price !== null && ev.price !== undefined) {
        currentPrice = ev.price;
      } else if (ev.type === "VOTE") {
        totalVotesSeen += 1;
        if (ev.vote.yes_price !== null && ev.vote.yes_price !== undefined) {
          currentPrice = ev.vote.yes_price;
        }
        currentP1 = ev.vote.p1_weighted_pct;
        currentP2 = ev.vote.p2_weighted_pct;
        currentP3 = ev.vote.p3_weighted_pct;
        currentP4 = ev.vote.p4_weighted_pct;
        currentAuthor = ev.vote.author_username;
        currentVoteType = ev.vote.vote_type;
      }

      const key = `${Math.round(ev.timeMs / 1000)}`; // 1-second precision
      if (!seenTimes.has(key)) {
        seenTimes.add(key);

        const d = new Date(ev.timestamp);
        const day = String(d.getUTCDate()).padStart(2, "0");
        const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        const month = months[d.getUTCMonth()];
        const hours = String(d.getUTCHours()).padStart(2, "0");
        const minutes = String(d.getUTCMinutes()).padStart(2, "0");
        const dateKey = `${day} ${month}`;
        const uniqueKey = `${day} ${month} ${hours}:${minutes}:${d.getUTCSeconds()}`;

        if (!seenDates.has(dateKey)) {
          seenDates.add(dateKey);
          midnights.push(uniqueKey);
          tickMap[uniqueKey] = dateKey;
        }

        // Only emit consensus trajectory points once at least 2 votes are in
        const hasMinVotes = totalVotesSeen >= 2;

        mergedPoints.push({
          timestamp: ev.timestamp,
          timeMs: ev.timeMs,
          uniqueKey: uniqueKey,
          timeFormatted: formatUTC(ev.timestamp, true, false),
          timeLabel: formatUTC(ev.timestamp, true, true), // DD MMM HH:mm
          p1: hasMinVotes ? currentP1 : null,
          p2: hasMinVotes ? currentP2 : null,
          p3: hasMinVotes ? currentP3 : null,
          p4: hasMinVotes ? currentP4 : null,
          yes_price_scaled: currentPrice * 100, // Scale to 0-100
          raw_price: currentPrice,
          author: ev.type === "VOTE" ? currentAuthor : null,
          vote_type: ev.type === "VOTE" ? currentVoteType : null,
          totalVotesSeen: totalVotesSeen,
        });
      }
    });

    // If multiple days exist, anchor ticks to 00:00 marks. Otherwise, take 5 evenly spaced intervals.
    let xTicks = midnights;
    if (xTicks.length < 2 && mergedPoints.length > 0) {
      const step = Math.max(1, Math.floor(mergedPoints.length / 5));
      const sampleTicks = [];
      for (let i = 0; i < mergedPoints.length; i += step) {
        sampleTicks.push(mergedPoints[i].uniqueKey);
        tickMap[mergedPoints[i].uniqueKey] = mergedPoints[i].timeLabel;
      }
      xTicks = sampleTicks;
    }

    return { chartData: mergedPoints, xTicks: xTicks, dateTickMap: tickMap };
  }, [consensusTrajectory, priceHistory]);

  const toggleExpand = (msgId) => {
    setExpandedMessageIds((prev) => {
      const next = new Set(prev);
      if (next.has(msgId)) next.delete(msgId);
      else next.add(msgId);
      return next;
    });
  };

  // Handle voter dot selection from distribution chart -> scroll & highlight chat feed
  const handleSelectVoter = (voter) => {
    if (!voter) return;
    const username = voter.author_username;
    setSelectedVoterUsername(username);

    if (!chatMessages || chatMessages.length === 0) return;

    const matchedMsg = chatMessages.find(
      (m) => m.author_username && m.author_username.toLowerCase() === username.toLowerCase()
    );

    if (matchedMsg) {
      setActiveMessageId(matchedMsg.message_id);
      setExpandedMessageIds((prev) => new Set(prev).add(matchedMsg.message_id));

      if (selectedStanceFilter !== "ALL" && matchedMsg.vote_type !== selectedStanceFilter) {
        setSelectedStanceFilter("ALL");
      }

      setTimeout(() => {
        const el = messageRefs.current[matchedMsg.message_id];
        if (el && chatContainerRef.current) {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }, 50);
    }
  };

  // Determine which outcomes actually have votes or non-zero consensus share
  const hasYES = (cohortCounts?.P2 || 0) > 0 || (voterDistribution || []).some(v => v.vote_type === "P2" || v.vote_type === "YES") || (consensusTrajectory || []).some(c => (c.p2_weighted_pct || 0) > 0);
  const hasNO = (cohortCounts?.P1 || 0) > 0 || (voterDistribution || []).some(v => v.vote_type === "P1" || v.vote_type === "NO") || (consensusTrajectory || []).some(c => (c.p1_weighted_pct || 0) > 0);
  const hasUNKNOWN = (cohortCounts?.P3 || 0) > 0 || (voterDistribution || []).some(v => v.vote_type === "P3" || v.vote_type === "UNKNOWN") || (consensusTrajectory || []).some(c => (c.p3_weighted_pct || 0) > 0);
  const hasEARLY = (cohortCounts?.P4 || 0) > 0 || (voterDistribution || []).some(v => v.vote_type === "P4" || v.vote_type === "EARLY") || (consensusTrajectory || []).some(c => (c.p4_weighted_pct || 0) > 0);

  const filteredMessages = useMemo(() => {
    if (!chatMessages) return [];
    if (selectedStanceFilter === "ALL") return chatMessages;
    return chatMessages.filter((m) => m.vote_type === selectedStanceFilter);
  }, [chatMessages, selectedStanceFilter]);

  return (
    <div className="w-full grid grid-cols-1 lg:grid-cols-12 gap-4">
      {/* Left Side: Unified Dual-Axis Stepped Chart */}
      <div className="lg:col-span-7 rounded-xl border border-slate-800 bg-[#0e1524] p-4 shadow-md h-[380px] sm:h-[460px] lg:h-[550px] flex flex-col space-y-3">
        {/* Chart Header & Legend */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-xs font-bold text-slate-200">
            Consensus & Price History
          </h4>
          <div className="flex flex-wrap items-center gap-3 text-xs font-mono">
            <div className="flex items-center gap-1 text-cyan-400">
              <span className="h-2 w-2 rounded-full bg-cyan-400"></span>
              <span>YES Price (USD)</span>
            </div>
            <div className="flex items-center gap-2.5">
              {hasYES && (
                <span className="flex items-center gap-1 text-emerald-400 font-semibold">
                  <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
                  YES
                </span>
              )}
              {hasNO && (
                <span className="flex items-center gap-1 text-rose-400 font-semibold">
                  <span className="h-2 w-2 rounded-full bg-rose-500"></span>
                  NO
                </span>
              )}
              {hasUNKNOWN && (
                <span className="flex items-center gap-1 text-amber-400 font-semibold">
                  <span className="h-2 w-2 rounded-full bg-amber-500"></span>
                  UNKNOWN
                </span>
              )}
              {hasEARLY && (
                <span className="flex items-center gap-1 text-purple-400 font-semibold">
                  <span className="h-2 w-2 rounded-full bg-purple-500"></span>
                  EARLY
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Line Chart Area */}
        <div className="flex-1 w-full min-h-[250px] bg-slate-950/60 rounded-lg border border-slate-800 p-2">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid yAxisId="left" strokeDasharray="3 3" stroke="#1e293b" horizontal={true} vertical={true} />
                
                {/* X-Axis with Timestamps (DD MMM at 00:00 midnight ticks or interval ticks) */}
                <XAxis
                  dataKey="uniqueKey"
                  ticks={xTicks}
                  tickFormatter={(val) => dateTickMap[val] || val.split(" ").slice(0, 2).join(" ")}
                  stroke="#64748b"
                  fontSize={9.5}
                  tickLine={false}
                  axisLine={{ stroke: "#334155" }}
                />

                {/* Left Y-Axis: Price Scale ($0.00 to $1.00 at intervals of 0.20) */}
                <YAxis
                  yAxisId="left"
                  domain={[0, 100]}
                  ticks={[0, 20, 40, 60, 80, 100]}
                  stroke="#64748b"
                  fontSize={9.5}
                  tickFormatter={(v) => `$${(v / 100).toFixed(2)}`}
                  tickLine={false}
                  axisLine={{ stroke: "#334155" }}
                />

                {/* Right Y-Axis: Percent Share Scale (0% to 100% at intervals of 20%) */}
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  domain={[0, 100]}
                  ticks={[0, 20, 40, 60, 80, 100]}
                  stroke="#64748b"
                  fontSize={9.5}
                  tickFormatter={(v) => `${Math.round(v)}%`}
                  tickLine={false}
                  axisLine={{ stroke: "#334155" }}
                />

                {/* Vertical Grid Lines at Day/Interval Boundaries */}
                {xTicks.map((mKey) => (
                  <ReferenceLine
                    key={`grid-${mKey}`}
                    x={mKey}
                    stroke="#1e293b"
                    strokeDasharray="2 2"
                    strokeWidth={1}
                  />
                ))}

                <Tooltip
                  isAnimationActive={false}
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload;
                      const outcomeLabel = data.vote_type === "P2" ? "YES" : data.vote_type === "P1" ? "NO" : data.vote_type === "P3" ? "UNKNOWN" : data.vote_type === "P4" ? "EARLY" : data.vote_type;
                      return (
                        <div className="rounded-lg border border-slate-700 bg-slate-900/95 p-2.5 shadow-2xl backdrop-blur-md text-xs font-mono space-y-1">
                          <div className="text-slate-400 font-semibold border-b border-slate-800 pb-1">
                            {data.timeFormatted}
                          </div>
                          {data.author && (
                            <div className="text-slate-300">
                              Vote: <span className="font-bold text-white">@{data.author}</span> ({outcomeLabel})
                            </div>
                          )}
                          {data.p2 !== null ? (
                            <>
                              {hasYES && <div className="text-emerald-400">YES: {Math.round(data.p2 || 0)}%</div>}
                              {hasNO && <div className="text-rose-400">NO: {Math.round(data.p1 || 0)}%</div>}
                              {hasUNKNOWN && <div className="text-amber-400">UNKNOWN: {Math.round(data.p3 || 0)}%</div>}
                              {hasEARLY && <div className="text-purple-400">EARLY: {Math.round(data.p4 || 0)}%</div>}
                            </>
                          ) : (
                            <div className="text-slate-400 text-[10px] italic py-0.5">
                              Consensus trajectory starts at ≥ 2 votes
                            </div>
                          )}
                          <div className="text-cyan-400 pt-1 border-t border-slate-800 font-bold">
                            YES Price: ${data.raw_price?.toFixed(3)}
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />

                {/* Solid Thin Cyan Orderbook YES Price curve */}
                <Line
                  yAxisId="left"
                  type="stepAfter"
                  dataKey="yes_price_scaled"
                  stroke="#06b6d4"
                  strokeWidth={1.4}
                  dot={false}
                  isAnimationActive={false}
                  name="YES Price"
                />

                {/* Stepped Consensus Curves (Only present outcomes plotted) */}
                {hasYES && (
                  <Line
                    yAxisId="right"
                    type="stepAfter"
                    dataKey="p2"
                    stroke="#10b981"
                    strokeWidth={1.4}
                    dot={false}
                    isAnimationActive={false}
                    name="YES"
                  />
                )}
                {hasNO && (
                  <Line
                    yAxisId="right"
                    type="stepAfter"
                    dataKey="p1"
                    stroke="#f43f5e"
                    strokeWidth={1.4}
                    dot={false}
                    isAnimationActive={false}
                    name="NO"
                  />
                )}
                {hasUNKNOWN && (
                  <Line
                    yAxisId="right"
                    type="stepAfter"
                    dataKey="p3"
                    stroke="#f59e0b"
                    strokeWidth={1.4}
                    dot={false}
                    isAnimationActive={false}
                    name="UNKNOWN"
                  />
                )}
                {hasEARLY && (
                  <Line
                    yAxisId="right"
                    type="stepAfter"
                    dataKey="p4"
                    stroke="#a855f7"
                    strokeWidth={1.4}
                    dot={false}
                    isAnimationActive={false}
                    name="EARLY"
                  />
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Right Side: Top Voter Dot Map + Bottom Chat Feed */}
        <div className="lg:col-span-5 flex flex-col gap-4 h-auto lg:h-[550px]">
          {/* Top: Voter Distribution Strip Map */}
          <div className="shrink-0">
            <VoterDistributionChart
              voterDistribution={voterDistribution || []}
              cohortRms={cohortRms || {}}
              cohortCounts={cohortCounts || {}}
              consensusTrajectory={consensusTrajectory || []}
              minCompetencyPct={minCompetencyPct}
              selectedVoterUsername={selectedVoterUsername}
              onSelectVoter={handleSelectVoter}
            />
          </div>

          {/* Bottom: Dispute Thread Chat Replay Feed */}
          <div className="h-[380px] lg:flex-1 rounded-xl border border-slate-800 bg-[#0e1524] p-4 shadow-md flex flex-col overflow-hidden space-y-3">
            {/* Header */}
            <div className="flex items-center justify-between pb-2 border-b border-slate-800 shrink-0">
              <div className="flex items-center gap-2">
                <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                  <MessageSquare className="h-3.5 w-3.5 text-slate-400" />
                  Dispute Discussion Feed
                </h4>
                <span className="rounded bg-slate-800 px-1.5 py-0.2 text-[10px] font-mono text-slate-400">
                  {filteredMessages.length}
                </span>
              </div>

              <select
                value={selectedStanceFilter}
                onChange={(e) => setSelectedStanceFilter(e.target.value)}
                className="rounded bg-slate-900 border border-slate-700 py-0.5 px-2 text-[10px] text-slate-300 font-mono focus:border-slate-500 focus:outline-none"
              >
                <option value="ALL">All Stances</option>
                {hasYES && <option value="P2">YES</option>}
                {hasNO && <option value="P1">NO</option>}
                {hasUNKNOWN && <option value="P3">UNKNOWN</option>}
                {hasEARLY && <option value="P4">EARLY</option>}
              </select>
            </div>

            {/* Chat Stream List */}
            <div ref={chatContainerRef} className="flex-1 overflow-y-auto space-y-2 pr-1 pt-2">
              {filteredMessages.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-500 font-mono">
                  No messages found for this filter.
                </div>
              ) : (
                filteredMessages.map((msg) => {
                  const isActive = activeMessageId === msg.message_id;
                  const isExpanded = expandedMessageIds.has(msg.message_id);
                  const isLong = msg.content && msg.content.length > 200;
                  const displayContent = isLong && !isExpanded ? msg.content.slice(0, 200) + "..." : msg.content;

                  let badgeColor = "bg-slate-800 text-slate-400 border-slate-700";
                  let outcomeDisplay = msg.vote_type;
                  if (msg.vote_type === "P2") {
                    badgeColor = "bg-emerald-500/15 text-emerald-300 border-emerald-500/40";
                    outcomeDisplay = "YES (P2)";
                  } else if (msg.vote_type === "P1") {
                    badgeColor = "bg-rose-500/15 text-rose-300 border-rose-500/40";
                    outcomeDisplay = "NO (P1)";
                  } else if (msg.vote_type === "P3") {
                    badgeColor = "bg-amber-500/15 text-amber-300 border-amber-500/40";
                    outcomeDisplay = "UNKNOWN (P3)";
                  } else if (msg.vote_type === "P4") {
                    badgeColor = "bg-purple-500/15 text-purple-300 border-purple-500/40";
                    outcomeDisplay = "EARLY (P4)";
                  }

                  return (
                    <div
                      key={msg.message_id}
                      ref={(el) => (messageRefs.current[msg.message_id] = el)}
                      className={`rounded-lg p-2 transition-all text-xs border ${
                        isActive
                          ? "border-slate-500/90 bg-slate-800/40 shadow-md ring-1 ring-slate-400/40 chat-highlight"
                          : "border-slate-800/80 bg-slate-900/40 hover:bg-slate-900/80"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-1.5 mb-1">
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-slate-200">@{msg.author_username}</span>
                          {msg.vote_type && (
                            <span className={`rounded px-1.5 py-0.2 font-mono text-[9px] font-bold border ${badgeColor}`}>
                              {outcomeDisplay}
                            </span>
                          )}
                        </div>
                        <span className="font-mono text-[9.5px] text-slate-500">
                          {formatUTC(msg.timestamp, true, true)}
                        </span>
                      </div>

                      <div className="text-slate-300 leading-relaxed font-sans text-[11px] break-words">
                        <MarkdownRenderer content={displayContent} />
                        {isLong && (
                          <button
                            onClick={() => toggleExpand(msg.message_id)}
                            className="mt-1 inline-flex items-center gap-1 text-[10px] font-sans text-slate-400 hover:text-slate-200 transition-colors py-0.5 px-1.5 rounded hover:bg-slate-800/80 cursor-pointer select-none border border-transparent hover:border-slate-700/60"
                          >
                            <span>{isExpanded ? "Show less" : "Show more"}</span>
                            {isExpanded ? (
                              <ChevronUp className="h-2.5 w-2.5" />
                            ) : (
                              <ChevronDown className="h-2.5 w-2.5" />
                            )}
                          </button>
                        )}
                      </div>

                      {msg.urls && msg.urls.length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {msg.urls.map((u, uIdx) => (
                            <a
                              key={uIdx}
                              href={u}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 rounded bg-slate-800 px-1.5 py-0.5 text-[8.5px] font-mono text-slate-300 hover:text-white border border-slate-700 max-w-[180px] truncate"
                            >
                              <ExternalLink className="h-2.5 w-2.5" />
                              <span className="truncate">{u.replace(/^https?:\/\//, "")}</span>
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }
