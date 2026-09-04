import { AlertTriangle, RefreshCw, Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import DisputeAnalysisPanel from "./components/DisputeAnalysisPanel";
import Navbar from "./components/Navbar";
import ScreenerTable from "./components/ScreenerTable";
import SettingsModal from "./components/SettingsModal";
import TabLeaderboardPlaceholder from "./components/TabLeaderboardPlaceholder";
import TabMethodologyPlaceholder from "./components/TabMethodologyPlaceholder";
import { fetchHealth, fetchMarketDetail, fetchScreenerMarkets } from "./lib/api";

export const defaultSettings = {
  minExperienceVotes: 10,
  minCompetencyPct: 50,
  trustNumber: 20,
  priorScore: 0.50,
  weightingMethod: "S^2"
};

export default function App() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [settings, setSettings] = useState(defaultSettings);

  // Health state
  const [health, setHealth] = useState(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState(null);

  // Screener markets state
  const [markets, setMarkets] = useState([]);
  const [marketsLoading, setMarketsLoading] = useState(true);
  const [marketsError, setMarketsError] = useState(null);

  // Selected market state
  const [selectedMarketId, setSelectedMarketId] = useState(null);
  const [selectedMarketDetail, setSelectedMarketDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);

  // Fetch health check
  const checkHealth = useCallback(async () => {
    try {
      setHealthLoading(true);
      const data = await fetchHealth();
      setHealth(data);
      setHealthError(null);
      return data;
    } catch (err) {
      setHealthError(err.message);
      setHealth(null);
      return null;
    } finally {
      setHealthLoading(false);
    }
  }, []);

  // Fetch screener markets
  const loadMarkets = useCallback(async () => {
    try {
      setMarketsLoading(true);
      setMarketsError(null);
      const data = await fetchScreenerMarkets({ status: "all", limit: 3000 });
      setMarkets(data.markets || []);
    } catch (err) {
      setMarketsError(err.message);
      setMarkets([]);
    } finally {
      setMarketsLoading(false);
    }
  }, []);

  // Initial load & periodic health poll
  useEffect(() => {
    let intervalId;

    const init = async () => {
      const h = await checkHealth();
      if (h && h.database === "connected") {
        await loadMarkets();
      }
    };

    init();

    // Poll health every 20 seconds
    intervalId = setInterval(() => {
      checkHealth();
    }, 20000);

    return () => clearInterval(intervalId);
  }, [checkHealth, loadMarkets]);

  // Fetch detailed market analysis when selection changes
  useEffect(() => {
    if (!selectedMarketId) {
      setSelectedMarketDetail(null);
      return;
    }

    let isCurrent = true;
    setDetailLoading(true);
    setDetailError(null);

    const powerExponent = settings.weightingMethod === "S^3" ? 3.0 : settings.weightingMethod === "S" ? 1.0 : 2.0;

    fetchMarketDetail(selectedMarketId, {
      trustNumber: settings.trustNumber,
      priorScore: settings.priorScore,
      powerExponent: powerExponent,
      minAccuracy: settings.minCompetencyPct,
    })
      .then((detail) => {
        if (isCurrent) {
          setSelectedMarketDetail(detail);
          setDetailLoading(false);
        }
      })
      .catch((err) => {
        if (isCurrent) {
          setDetailError(err.message);
          setDetailLoading(false);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [selectedMarketId, settings]);

  // Live disputes count
  const liveDisputesCount = useMemo(() => {
    return markets.filter((m) => m.is_live_dispute).length;
  }, [markets]);

  // Offline detection (Zero-Mock Policy)
  const isOffline = !!healthError || !!marketsError || (health && health.database !== "connected");

  const handleManualRetry = async () => {
    const h = await checkHealth();
    if (h && h.database === "connected") {
      await loadMarkets();
    }
  };

  return (
    <div className="min-h-screen bg-[#080c14] text-slate-100 flex flex-col font-sans selection:bg-slate-700 selection:text-slate-100">
      {/* Top Navigation Bar with live telemetry */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onOpenSettings={() => setIsSettingsOpen(true)}
        liveDisputesCount={liveDisputesCount}
        health={health}
        healthLoading={healthLoading}
        onRetryHealth={handleManualRetry}
      />

      {/* Main Content Area */}
      <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 py-4 space-y-4">
        {/* OFFLINE SCREEN (Zero-Mock Fallback Policy) */}
        {isOffline ? (
          <div className="my-12 max-w-2xl mx-auto rounded-2xl border border-rose-800/60 bg-[#0e1320] p-8 shadow-2xl text-center space-y-5">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-500/15 border border-rose-500/30 text-rose-400">
              <AlertTriangle className="h-7 w-7" />
            </div>

            <div className="space-y-2">
              <h2 className="text-xl font-bold text-slate-100">
                System Offline — Database Connection Required
              </h2>
              <p className="text-sm text-slate-400 max-w-md mx-auto leading-relaxed">
                Polydispute requires an active connection to the MotherDuck cloud data warehouse.
                Prediction market analytics and live dispute trajectories cannot be loaded.
              </p>
            </div>

            {/* Diagnostic Box */}
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4 font-mono text-xs text-left space-y-2 max-w-lg mx-auto">
              <div className="flex items-center justify-between text-slate-400">
                <span>Database Target:</span>
                <span className="text-cyan-300 font-semibold">{health?.database_target || "md:polydispute_dev"}</span>
              </div>
              <div className="flex items-center justify-between text-slate-400">
                <span>Database State:</span>
                <span className="text-rose-400 font-semibold">{health?.database || "unreachable"}</span>
              </div>
              {(healthError || marketsError) && (
                <div className="pt-2 border-t border-slate-800 text-rose-300 break-words">
                  <span>Error: </span>
                  <span className="text-slate-400">{healthError || marketsError}</span>
                </div>
              )}
            </div>

            <div>
              <button
                onClick={handleManualRetry}
                disabled={healthLoading}
                className="inline-flex items-center gap-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white px-5 py-2.5 text-xs font-semibold shadow-lg shadow-cyan-600/20 transition-all cursor-pointer disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${healthLoading ? "animate-spin" : ""}`} />
                <span>{healthLoading ? "Connecting..." : "Retry Connection"}</span>
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* TAB 1: MAIN DASHBOARD */}
            {activeTab === "dashboard" && (
              <div className="space-y-4">
                {marketsLoading && markets.length === 0 ? (
                  <div className="rounded-xl border border-slate-800 bg-[#0d1322] p-16 text-center space-y-4">
                    <div className="relative mx-auto flex h-12 w-12 items-center justify-center">
                      <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
                    </div>
                    <p className="text-xs font-mono text-slate-400">
                      Connecting to MotherDuck & loading live dispute catalog...
                    </p>
                  </div>
                ) : !selectedMarketId ? (
                  <ScreenerTable
                    markets={markets}
                    selectedMarketId={selectedMarketId}
                    onSelectMarket={(id) => setSelectedMarketId(id)}
                  />
                ) : detailLoading ? (
                  <div className="rounded-xl border border-slate-800 bg-[#0d1322] p-16 text-center space-y-4">
                    <div className="relative mx-auto flex h-12 w-12 items-center justify-center">
                      <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm font-semibold text-slate-200">
                        Loading Market #{selectedMarketId}
                      </p>
                      <p className="text-xs font-mono text-slate-400">
                        Calculating...
                      </p>
                    </div>
                  </div>
                ) : detailError ? (
                  <div className="rounded-xl border border-rose-800/50 bg-rose-950/20 p-8 text-center space-y-3">
                    <p className="text-sm font-semibold text-rose-300">Failed to load market detail</p>
                    <p className="text-xs font-mono text-slate-400">{detailError}</p>
                    <button
                      onClick={() => setSelectedMarketId(null)}
                      className="rounded-lg bg-slate-800 px-4 py-1.5 text-xs text-slate-200 hover:bg-slate-700 transition-colors"
                    >
                      Back to Screener
                    </button>
                  </div>
                ) : (
                  <div>
                    <DisputeAnalysisPanel
                      marketDetail={selectedMarketDetail}
                      onClose={() => setSelectedMarketId(null)}
                      minCompetencyPct={settings.minCompetencyPct}
                    />
                  </div>
                )}
              </div>
            )}

            {/* TAB 2: VOTER CALIBRATION LEADERBOARD */}
            {activeTab === "leaderboard" && (
              <TabLeaderboardPlaceholder
                minCompetencyPct={settings.minCompetencyPct}
                minPredictions={settings.minExperienceVotes}
              />
            )}

            {/* TAB 3: METHODOLOGY (Feature-flagged off) */}
            {false && activeTab === "methodology" && <TabMethodologyPlaceholder />}
          </>
        )}
      </main>

      {/* Global Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        settings={settings}
        setSettings={setSettings}
        defaultSettings={defaultSettings}
      />
    </div>
  );
}
