import { cn } from '@/lib/utils'

export function DataTable({ columns, data, onRowClick, emptyMessage = 'NO DATA AVAILABLE' }) {
  if (!data || data.length === 0) {
    return (
      <div className="w-full text-center text-xs font-mono text-muted-foreground py-8">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="w-full overflow-x-auto text-xs font-mono">
      <table className="w-full text-left border-collapse">
        <thead>
          <tr className="border-b border-border/50 text-muted-foreground">
            {columns.map((col) => (
              <th
                key={col.key}
                className={cn(
                  "py-2 pr-4 font-normal",
                  col.align === 'right' && 'text-right pr-0 pl-4'
                )}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr
              key={row.id || i}
              className={cn(
                "border-b border-border/30 hover:bg-muted/30 transition-colors",
                onRowClick && "cursor-pointer"
              )}
              onClick={() => onRowClick?.(row)}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={cn(
                    "py-2 pr-4",
                    col.align === 'right' && 'text-right pr-0 pl-4',
                    col.className
                  )}
                >
                  {col.render ? col.render(row[col.key], row) : row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
