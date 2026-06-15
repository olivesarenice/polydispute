import { cn } from '@/lib/utils'

export function StatusBadge({ status }) {
  const styles = {
    proposed: 'text-accent border-accent/50',
    disputed: 'text-destructive border-destructive/50 pulse-glow',
    resolved: 'text-muted-foreground border-muted-foreground/50',
    default: 'text-foreground border-border',
  }

  const key = status?.toLowerCase() || 'default'
  const style = styles[key] || styles.default

  return (
    <span className={cn("border px-2 py-0.5 text-[10px] font-mono uppercase", style)}>
      {status || '—'}
    </span>
  )
}


export function VoteBar({ p1 = 0, p2 = 0, p3 = 0, p4 = 0 }) {
  const total = p1 + p2 + p3 + p4
  if (total === 0) return <span className="text-muted-foreground text-[10px]">NO VOTES</span>

  const pct = (v) => ((v / total) * 100).toFixed(0) + '%'

  return (
    <div className="flex items-center gap-1 text-[10px] font-mono">
      <div className="flex h-3 w-24 overflow-hidden border border-border/50">
        {p1 > 0 && <div className="bg-primary/80 h-full" style={{ width: pct(p1) }} title={`P1: ${p1}`} />}
        {p2 > 0 && <div className="bg-destructive/80 h-full" style={{ width: pct(p2) }} title={`P2: ${p2}`} />}
        {p3 > 0 && <div className="bg-accent/60 h-full" style={{ width: pct(p3) }} title={`P3: ${p3}`} />}
        {p4 > 0 && <div className="bg-muted-foreground/60 h-full" style={{ width: pct(p4) }} title={`P4: ${p4}`} />}
      </div>
      <span className="text-muted-foreground">{total}</span>
    </div>
  )
}


export function MetricBox({ label, value, sub, className }) {
  return (
    <div className={cn("border border-border p-3", className)}>
      <div className="text-[10px] text-muted-foreground tracking-widest mb-1">{label}</div>
      <div className="text-lg font-mono glow-text">{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground mt-1">{sub}</div>}
    </div>
  )
}
