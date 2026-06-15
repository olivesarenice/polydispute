import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'

const CHART_COLORS = {
  primary: 'hsl(135 60% 55%)',
  accent: 'hsl(50 90% 70%)',
  danger: 'hsl(0 84% 60%)',
  muted: 'hsl(135 40% 45%)',
  border: 'hsl(135 40% 30%)',
  bg: 'hsl(135 15% 12%)',
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null

  return (
    <div className="border border-border bg-background p-2 text-xs font-mono">
      <p className="text-muted-foreground mb-1">{label}</p>
      {payload.map((entry, i) => (
        <p key={i} style={{ color: entry.color }}>
          {entry.name}: {typeof entry.value === 'number' ? entry.value.toFixed(2) : entry.value}
        </p>
      ))}
    </div>
  )
}

export function JaggedChart({
  data,
  dataKey = 'value',
  xKey = 'step',
  height = 200,
  color = CHART_COLORS.primary,
  secondaryDataKey,
  secondaryColor = CHART_COLORS.accent,
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}>
        <CartesianGrid
          strokeDasharray="3 3"
          stroke={CHART_COLORS.border}
          horizontal={true}
          vertical={true}
        />
        <XAxis
          dataKey={xKey}
          stroke={CHART_COLORS.muted}
          fontSize={10}
          tickLine={false}
          axisLine={{ stroke: CHART_COLORS.border }}
          fontFamily="'Courier New', monospace"
        />
        <YAxis
          stroke={CHART_COLORS.muted}
          fontSize={10}
          tickLine={false}
          axisLine={{ stroke: CHART_COLORS.border }}
          domain={['auto', 'auto']}
          fontFamily="'Courier New', monospace"
        />
        <Tooltip content={<CustomTooltip />} />
        <Line
          type="linear"
          dataKey={dataKey}
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
          name={dataKey}
        />
        {secondaryDataKey && (
          <Line
            type="linear"
            dataKey={secondaryDataKey}
            stroke={secondaryColor}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
            name={secondaryDataKey}
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  )
}
