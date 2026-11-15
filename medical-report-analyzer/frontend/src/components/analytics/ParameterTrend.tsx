/**
 * src/components/analytics/ParameterTrend.tsx
 * Glass-finish parameter trend explorer: pill selector + line chart with
 * reference band and status-colored points.
 */
import { useMemo, useState, type FC } from 'react'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceArea, Dot,
} from 'recharts'
import type { ParameterTrend as TrendData } from './trends'
import Icon from '../common/Icon'

const STATUS_COLOR: Record<string, string> = {
  Normal: '#10b981',
  Low: '#0b63e5',
  High: '#f59e0b',
  Critical: '#ef4444',
  Unknown: '#94a3b8',
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const StatusDot: FC<any> = (props) => {
  const { cx, cy, payload } = props
  if (cx == null || cy == null) return null
  return <Dot cx={cx} cy={cy} r={4} fill={STATUS_COLOR[payload?.status] ?? '#94a3b8'} stroke="#fff" strokeWidth={1.5} />
}

const ParameterTrend: FC<{ trends: TrendData[] }> = ({ trends: initial }) => {
  const trends = useMemo(() => initial.filter(t => t.points.length > 0), [initial])
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const selected = trends.find(t => t.key === selectedKey) ?? trends[0]

  if (trends.length === 0) {
    return (
      <div className="card text-center py-14">
        <span className="mx-auto mb-4 w-14 h-14 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center">
          <Icon name="trendingUp" className="w-6 h-6" />
        </span>
        <p className="font-semibold text-slate-800">No trends yet</p>
        <p className="text-sm text-slate-500 mt-1">
          Upload and analyse at least one report to see parameter trends here.
        </p>
      </div>
    )
  }
  if (!selected) return null

  const band = selected.points.find(p => p.refLow != null || p.refHigh != null)
  const values = selected.points.map(p => p.value)
  const dataMin = Math.min(...values)
  const dataMax = Math.max(...values)
  const pad = Math.max((dataMax - dataMin) * 0.25, Math.abs(dataMax) * 0.05, 1)
  const domain: [number, number] = [
    Math.min(dataMin - pad, band?.refLow ?? Infinity),
    Math.max(dataMax + pad, band?.refHigh ?? -Infinity),
  ]

  return (
    <div className="flex flex-col gap-4">
      {/* Parameter selector */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {trends.map(t => (
          <button
            key={t.key}
            onClick={() => setSelectedKey(t.key)}
            className={`radius-pill !px-4 !py-2 !text-xs whitespace-nowrap ${
              t.key === selected.key ? 'active' : 'bg-white/70'
            }`}
          >
            {t.displayName} <span className="opacity-60">({t.points.length})</span>
          </button>
        ))}
      </div>

      {/* Chart card */}
      <div className="card">
        <div className="flex items-center justify-between gap-3 flex-wrap mb-4">
          <div>
            <h3 className="font-semibold text-slate-900 text-lg">
              {selected.displayName}
              {selected.unit && <span className="text-sm font-normal text-slate-400"> · {selected.unit}</span>}
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              {selected.points.length} measurement{selected.points.length === 1 ? '' : 's'} · green band = reference range
            </p>
          </div>
          <div className="flex items-center gap-3 text-[11px] text-slate-500">
            {[['Normal', '#10b981'], ['Low', '#0b63e5'], ['High', '#f59e0b']].map(([label, color]) => (
              <span key={label} className="inline-flex items-center gap-1">
                <span className="w-2 h-2 rounded-full" style={{ background: color }} />{label}
              </span>
            ))}
          </div>
        </div>

        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={selected.points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,60,120,0.12)" />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
              <YAxis
                domain={domain}
                tick={{ fontSize: 11, fill: '#64748b' }}
                axisLine={false}
                tickLine={false}
                width={44}
              />
              <Tooltip
                contentStyle={{ borderRadius: 12, border: '1px solid rgba(15,60,120,0.12)', fontSize: 12 }}
                formatter={(value) => [`${value ?? ''} ${selected.unit}`, 'Value']}
                labelFormatter={(label) => `Report: ${label}`}
              />
              {band && band.refLow != null && band.refHigh != null && (
                <ReferenceArea y1={band.refLow} y2={band.refHigh} fill="#10b981" fillOpacity={0.10} />
              )}
              <Line
                type="monotone"
                dataKey="value"
                stroke="#0b63e5"
                strokeWidth={2.5}
                dot={<StatusDot />}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Latest readings */}
      <div className="card !p-4">
        <h3 className="font-semibold text-slate-800 text-sm mb-3">All readings — {selected.displayName}</h3>
        <div className="flex flex-col gap-1">
          {[...selected.points].reverse().map((p, i) => (
            <div key={i} className="flex items-center gap-3 text-sm py-1.5 border-b border-slate-100 last:border-0">
              <span className="w-2 h-2 rounded-full shrink-0" style={{ background: STATUS_COLOR[p.status] ?? '#94a3b8' }} />
              <span className="text-slate-500 text-xs w-16 shrink-0">{p.date}</span>
              <span className="font-semibold text-slate-800">{p.value} <span className="font-normal text-slate-400 text-xs">{p.unit}</span></span>
              <span className={`badge ml-auto shrink-0 ${
                p.status === 'Normal' ? 'badge-analyzed' :
                p.status === 'Unknown' ? 'badge-uploaded' : 'badge-failed'
              }`}>{p.status}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default ParameterTrend
