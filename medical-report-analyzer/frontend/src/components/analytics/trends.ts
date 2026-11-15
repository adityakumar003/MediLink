/**
 * src/components/analytics/trends.ts
 * Build per-parameter time series from stored analysis results.
 * Pure functions — no network, no backend changes needed.
 */
import type { AnalysisResult } from '../../types/report.types'

export interface TrendPoint {
  date: string        // display label
  timestamp: number
  value: number
  status: string
  unit: string
  refLow: number | null
  refHigh: number | null
}

export interface ParameterTrend {
  key: string         // normalized name for grouping
  displayName: string // original name from the latest report
  unit: string
  points: TrendPoint[]
}

function normalizeKey(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, ' ')
}

function parseRangeBounds(ref: string | undefined): { low: number | null; high: number | null } {
  if (!ref) return { low: null, high: null }
  const interval = ref.match(/(-?\d+(?:\.\d+)?)\s*[-–]\s*(-?\d+(?:\.\d+)?)/)
  if (interval) return { low: parseFloat(interval[1]), high: parseFloat(interval[2]) }
  const less = ref.match(/[<≤]\s*(-?\d+(?:\.\d+)?)/)
  if (less) return { low: null, high: parseFloat(less[1]) }
  const greater = ref.match(/[>≥]\s*(-?\d+(?:\.\d+)?)/)
  if (greater) return { low: parseFloat(greater[1]), high: null }
  return { low: null, high: null }
}

/** Group numeric parameter values across reports, oldest → newest. */
export function buildTrends(analyses: AnalysisResult[]): ParameterTrend[] {
  const groups = new Map<string, ParameterTrend>()
  const ordered = [...analyses].sort(
    (a, b) => new Date(a.analyzed_at).getTime() - new Date(b.analyzed_at).getTime(),
  )
  for (const analysis of ordered) {
    const date = new Date(analysis.analyzed_at)
    const label = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    for (const p of analysis.parameters) {
      if (typeof p.value !== 'number' || !Number.isFinite(p.value)) continue
      const key = normalizeKey(p.name)
      const bounds = parseRangeBounds(p.reference_range)
      const point: TrendPoint = {
        date: label,
        timestamp: date.getTime(),
        value: p.value,
        status: p.status,
        unit: p.unit || '',
        refLow: bounds.low,
        refHigh: bounds.high,
      }
      const existing = groups.get(key)
      if (existing) {
        existing.points.push(point)
        existing.displayName = p.name
        if (!existing.unit && p.unit) existing.unit = p.unit
      } else {
        groups.set(key, { key, displayName: p.name, unit: p.unit || '', points: [point] })
      }
    }
  }
  // Most-measured parameters first.
  return [...groups.values()].sort((a, b) => b.points.length - a.points.length)
}
