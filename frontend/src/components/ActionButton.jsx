import { cn } from '@/lib/utils'

export function ActionButton({ children, onClick, variant = 'default', className, ...props }) {
  const variants = {
    default: 'bg-accent text-accent-foreground hover:bg-accent/80',
    outline: 'border border-border text-foreground hover:bg-secondary',
    danger: 'bg-destructive text-destructive-foreground hover:bg-destructive/80',
  }

  return (
    <button
      onClick={onClick}
      className={cn(
        "px-4 py-1 font-mono text-sm uppercase transition-colors cursor-pointer",
        variants[variant],
        className
      )}
      {...props}
    >
      {children}
    </button>
  )
}
