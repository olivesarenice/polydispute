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
  const [selectedMarketId, setSelectedMarketId] = useState("3121262"); // default to live dispute market

  // Count live disputes
  const liveDisputesCount = useMemo(() => {
    return mockScreenerMarkets.filter((m) => m.is_live_dispute).length;
  }, []);

  // Fetch detailed data for selected market
  const selectedMarketDetail = useMemo(() => {
    if (!selectedMarketId) return null;
    return mockMarketDetails[selectedMarketId] || mockMarketDetails["3121262"] || null;
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
