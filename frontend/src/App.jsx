import { useState, useEffect, useCallback } from 'react'
import { fetchArbSignals, fetchHealth } from '@/lib/api'
import { MOCK_SIGNALS, MOCK_HEALTH } from '@/lib/mockData'
import { TerminalCard } from '@/components/TerminalCard'
import { DataTable } from '@/components/DataTable'
import { JaggedChart } from '@/components/JaggedChart'
import { ActionButton } from '@/components/ActionButton'
import { StatusBadge, VoteBar, MetricBox } from '@/components/Indicators'

function formatPct(v) {
  if (v == null) return '—'
  return (v * 100).toFixed(1) + '%'
}

function formatPrice(v) {
  if (v == null) return '—'
  return (v * 100).toFixed(1) + '¢'
}

function truncate(s, n = 50) {
  if (!s) return '—'
  return s.length > n ? s.slice(0, n) + '…' : s
}

const SIGNAL_COLUMNS = [
  {
    key: 'question',
    label: 'MARKET',
    render: (v) => <span className="text-foreground" title={v}>{truncate(v, 40)}</span>,
  },
  {
    key: 'yes_price',
    label: 'PM PRICE',
    align: 'right',
    render: (v) => formatPrice(v),
  },
  {
    key: 'tau_yes',
    label: 'τ(YES)',
    align: 'right',
    render: (v) => <span className="text-accent">{formatPct(v)}</span>,
  },
  {
    key: 'arb_spread',
    label: 'SPREAD',
    align: 'right',
    render: (v) => {
      const color = v > 0.15 ? 'text-edge-high' : v > 0.05 ? 'text-edge-mid' : 'text-edge-low'
      return <span className={`font-bold ${color}`}>{formatPct(v)}</span>
    },
  },
  {
    key: 'votes',
    label: 'VOTES',
    render: (_, row) => (
      <VoteBar p1={row.p1_votes} p2={row.p2_votes} p3={row.p3_votes} p4={row.p4_votes} />
    ),
  },
  {
    key: 'uma_resolution_status',
    label: 'STATUS',
    render: (v) => <StatusBadge status={v} />,
  },
]

export default function App() {
  const [signals, setSignals] = useState([])
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastSync, setLastSync] = useState(null)
  const [apiStatus, setApiStatus] = useState('OFFLINE')
  const [selectedSignal, setSelectedSignal] = useState(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [arbData, health] = await Promise.all([
        fetchArbSignals(),
        fetchHealth(),
      ])
      setSignals(arbData.signals)
      setCount(arbData.count)
      setApiStatus(health.status === 'ok' ? 'ONLINE' : 'DEGRADED')
      setLastSync(new Date().toISOString().replace('T', ' ').slice(0, 19) + 'Z')
    } catch (err) {
      // Fallback to mock data when backend is unavailable
      console.warn('API unavailable, loading mock data:', err.message)
      setSignals(MOCK_SIGNALS.signals)
      setCount(MOCK_SIGNALS.count)
      setApiStatus('MOCK')
      setLastSync('USING MOCK DATA')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  // Compute aggregate metrics
  const activeDisputes = signals.filter(s => s.uma_resolution_status === 'proposed' || s.uma_resolution_status === 'disputed').length
  const avgSpread = signals.length > 0
    ? signals.reduce((acc, s) => acc + (s.arb_spread || 0), 0) / signals.length
    : 0
  const maxSpread = signals.length > 0
    ? Math.max(...signals.map(s => s.arb_spread || 0))
    : 0

  // Build chart data from signals (spread distribution)
  const chartData = signals
    .filter(s => s.arb_spread != null)
    .map((s, i) => ({
      step: i + 1,
      spread: +(s.arb_spread * 100).toFixed(1),
      price: s.yes_price != null ? +(s.yes_price * 100).toFixed(1) : null,
    }))

  return (
    <div className="min-h-screen bg-background text-foreground p-6 font-mono uppercase">
      {/* Scanline overlay */}
      <div className="scanline" />

      {/* HEADER */}
      <header className="flex justify-between items-center mb-6 border-b border-border pb-4">
        <div>
          <h1 className="font-serif text-3xl lowercase mb-1 glow-text">polydispute</h1>
          <span className="text-[10px] tracking-widest text-muted-foreground">
            SYSTEM_STATUS: <span className={apiStatus === 'ONLINE' ? 'text-primary' : 'text-destructive'}>{apiStatus}</span>
            {lastSync && <span className="ml-4">LAST_SYNC: {lastSync}</span>}
          </span>
        </div>
        <ActionButton onClick={loadData} disabled={loading}>
          {loading ? 'SYNCING...' : 'SYNC_DATA'}
        </ActionButton>
      </header>

      {/* ERROR STATE */}
      {error && (
        <div className="border border-destructive/50 p-3 mb-6 text-xs text-destructive">
          ERR: {error}
        </div>
      )}

      {/* METRICS ROW */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <MetricBox label="TOTAL SIGNALS" value={count} />
        <MetricBox label="ACTIVE DISPUTES" value={activeDisputes} />
        <MetricBox label="AVG SPREAD" value={formatPct(avgSpread)} />
        <MetricBox label="MAX SPREAD" value={formatPct(maxSpread)} sub={maxSpread > 0.1 ? '⚡ EDGE DETECTED' : null} />
      </div>

      {/* MAIN GRID */}
      <main className="grid grid-cols-1 lg:grid-cols-12 gap-6">

        {/* LEFT: Signals Table */}
        <div className="lg:col-span-7">
          <TerminalCard title="ARB_SIGNALS" metric={`${count} ROWS`}>
            {loading ? (
              <div className="text-center text-xs text-muted-foreground py-8 pulse-glow">
                LOADING DATA...
              </div>
            ) : (
              <DataTable
                columns={SIGNAL_COLUMNS}
                data={signals}
                onRowClick={(row) => setSelectedSignal(row)}
              />
            )}
          </TerminalCard>
        </div>

        {/* RIGHT: Charts + Detail */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          <TerminalCard title="METRIC: SPREAD_DISTRIBUTION">
            <JaggedChart
              data={chartData}
              dataKey="spread"
              xKey="step"
              height={180}
            />
          </TerminalCard>

          <TerminalCard title="METRIC: PM_PRICE_vs_TAU">
            <JaggedChart
              data={chartData}
              dataKey="price"
              xKey="step"
              height={180}
              secondaryDataKey="spread"
              color="hsl(50 90% 70%)"
              secondaryColor="hsl(135 60% 55%)"
            />
          </TerminalCard>

          {/* Selected signal detail */}
          {selectedSignal && (
            <TerminalCard title="DETAIL" metric={selectedSignal.condition_id?.slice(0, 10) + '…'}>
              <div className="text-xs space-y-2">
                <div>
                  <span className="text-muted-foreground">QUESTION: </span>
                  <span className="normal-case">{selectedSignal.question}</span>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div><span className="text-muted-foreground">PM_YES: </span>{formatPrice(selectedSignal.yes_price)}</div>
                  <div><span className="text-muted-foreground">PM_NO: </span>{formatPrice(selectedSignal.no_price)}</div>
                  <div><span className="text-muted-foreground">TAU_YES: </span><span className="text-accent">{formatPct(selectedSignal.tau_yes)}</span></div>
                  <div><span className="text-muted-foreground">SPREAD: </span><span className="text-primary font-bold">{formatPct(selectedSignal.arb_spread)}</span></div>
                  <div><span className="text-muted-foreground">BOND: </span>{selectedSignal.uma_bond || '—'}</div>
                  <div><span className="text-muted-foreground">DOMINANT: </span>{selectedSignal.dominant_vote || '—'}</div>
                </div>
                <div className="pt-2 border-t border-border/30">
                  <span className="text-muted-foreground">VOTES: </span>
                  <span>P1={selectedSignal.p1_votes} P2={selectedSignal.p2_votes} P3={selectedSignal.p3_votes} P4={selectedSignal.p4_votes}</span>
                </div>
                {selectedSignal.slug && (
                  <div>
                    <a
                      href={`https://polymarket.com/event/${selectedSignal.slug}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent hover:text-accent/80 underline normal-case"
                    >
                      → View on Polymarket
                    </a>
                  </div>
                )}
              </div>
            </TerminalCard>
          )}
        </div>
      </main>

      {/* FOOTER */}
      <footer className="mt-8 pt-4 border-t border-border/30 text-[10px] text-muted-foreground flex justify-between">
        <span>POLYDISPUTE v3.1 // UMA DVM EDGE TRACKER</span>
        <span>DATA: POLYMARKET + DISCORD + POLYGON</span>
      </footer>
    </div>
  )
}
