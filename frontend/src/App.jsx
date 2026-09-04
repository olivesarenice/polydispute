import React, { useState, useMemo } from "react";
import Navbar from "./components/Navbar";
import SettingsModal from "./components/SettingsModal";
import ScreenerTable from "./components/ScreenerTable";
import DisputeAnalysisPanel from "./components/DisputeAnalysisPanel";
import TabLeaderboardPlaceholder from "./components/TabLeaderboardPlaceholder";
import TabMethodologyPlaceholder from "./components/TabMethodologyPlaceholder";
import { mockScreenerMarkets, mockMarketDetails, mockDefaultSettings } from "./mock/mockData";

export default function App() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [settings, setSettings] = useState(mockDefaultSettings);
  const [selectedMarketId, setSelectedMarketId] = useState(null);

  // Count live disputes
  const liveDisputesCount = useMemo(() => {
    return mockScreenerMarkets.filter((m) => m.is_live_dispute).length;
  }, []);

  // Fetch detailed data for selected market
  const selectedMarketDetail = useMemo(() => {
    if (!selectedMarketId) return null;
    if (mockMarketDetails && mockMarketDetails[selectedMarketId]) {
      return mockMarketDetails[selectedMarketId];
    }

    // Match the selected market from the screener dataset
    const base = mockScreenerMarkets.find((m) => String(m.market_id) === String(selectedMarketId));
    if (!base) {
      return mockMarketDetails ? Object.values(mockMarketDetails)[0] || null : null;
    }

    const yesP = base.yes_price ?? 0.5;
    const noP = base.no_price ?? 0.5;
    const p1 = base.p1_votes || 0;
    const p2 = base.p2_votes || 0;
    const p3 = base.p3_votes || 0;
    const p4 = base.p4_votes || 0;
    const totalV = base.total_voters || (p1 + p2 + p3 + p4) || 0;
    const roundStart = base.latest_dispute_started || "2026-08-01T00:00:00Z";
    const roundEnd = base.market_closed_time || "2026-08-03T00:00:00Z";

    return {
      market_id: String(base.market_id),
      question: base.question,
      slug: base.slug || `market-${base.market_id}`,
      description: base.description || "No market resolution description available.",
      market_status_code: base.market_status_code,
      market_status_label: base.market_status_label,
      yes_price: yesP,
      no_price: noP,
      best_bid: Math.max(0.01, parseFloat((yesP - 0.02).toFixed(3))),
      best_bid_shares: 12500,
      best_ask: Math.min(0.99, parseFloat((yesP + 0.02).toFixed(3))),
      best_ask_shares: 18400,
      consensus_price_delta: parseFloat(((p2 / (totalV || 1)) - yesP).toFixed(3)),
      dispute_rounds: [
        {
          round_num: 1,
          round_start: roundStart,
          round_end: roundEnd,
          assertion_id: `0x${base.market_id}a1b2c3d4e5f6`,
          total_votes: totalV,
        },
      ],
      price_history: [
        { timestamp: roundStart, yes_price: yesP },
        { timestamp: roundEnd, yes_price: yesP },
      ],
      consensus_trajectory: [
        {
          timestamp: roundStart,
          p1_pct: totalV > 0 ? p1 / totalV : 0,
          p2_pct: totalV > 0 ? p2 / totalV : 0,
          p3_pct: totalV > 0 ? p3 / totalV : 0,
          p4_pct: totalV > 0 ? p4 / totalV : 0,
        },
      ],
      voter_distribution: [],
      cohort_rms: { P1: 0.65, P2: 0.72, P3: 0.50, P4: 0.81 },
      cohort_counts: { P1: p1, P2: p2, P3: p3, P4: p4 },
      chat_messages: [],
    };
  }, [selectedMarketId]);

  const handleSelectMarket = (marketId) => {
    setSelectedMarketId(marketId);
  };

  const handleCloseAnalysis = () => {
    setSelectedMarketId(null);
  };

  return (
    <div className="min-h-screen bg-[#080c14] text-slate-100 flex flex-col font-sans selection:bg-slate-700 selection:text-slate-100">
      {/* Top Navigation */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onOpenSettings={() => setIsSettingsOpen(true)}
        liveDisputesCount={liveDisputesCount}
      />

      {/* Main Content Viewport */}
      <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 py-4 space-y-4">
        {/* TAB 1: MAIN DASHBOARD (Screener View OR Analysis Panel View) */}
        {activeTab === "dashboard" && (
          <div className="space-y-4">
            {!selectedMarketId ? (
              <ScreenerTable
                markets={mockScreenerMarkets}
                selectedMarketId={selectedMarketId}
                onSelectMarket={handleSelectMarket}
              />
            ) : (
              <div className="transition-all duration-300 animate-in fade-in slide-in-from-bottom-4">
                <DisputeAnalysisPanel
                  marketDetail={selectedMarketDetail}
                  onClose={handleCloseAnalysis}
                  minCompetencyPct={settings.minCompetencyPct}
                />
              </div>
            )}
          </div>
        )}

        {/* TAB 2: VOTER CALIBRATION LEADERBOARD */}
        {activeTab === "leaderboard" && (
          <TabLeaderboardPlaceholder minCompetencyPct={settings.minCompetencyPct} />
        )}

        {/* TAB 3: METHODOLOGY */}
        {activeTab === "methodology" && <TabMethodologyPlaceholder />}
      </main>

      {/* Global Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        settings={settings}
        setSettings={setSettings}
        defaultSettings={mockDefaultSettings}
      />
    </div>
  );
}
