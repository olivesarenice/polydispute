import { cn } from '@/lib/utils'

export function TerminalCard({ title, metric, children, className }) {
  return (
    <div className={cn("border border-border p-4 bg-background fade-in", className)}>
      <div className="mb-4 text-sm font-mono tracking-widest text-foreground/80 flex justify-between items-center">
        <span className="glow-text">[{title}]</span>
        {metric && <span className="text-xs text-muted-foreground">{metric}</span>}
      </div>
      <div className="w-full">
        {children}
      </div>
    </div>
  )
}
