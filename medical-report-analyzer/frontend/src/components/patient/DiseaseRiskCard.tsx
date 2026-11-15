/**
 * src/components/patient/DiseaseRiskCard.tsx
 * Preliminary assessment card: renders the backend assessment state —
 * a risk category only when supported, otherwise evidence/missing info
 * with explicit decision-support wording. Never a diagnosis.
 */
import type { FC } from 'react'
import type { DiseaseRiskItem } from '../../types/report.types'
import Icon, { type IconName } from '../common/Icon'

interface DiseaseRiskCardProps {
  disease: string
  risk: DiseaseRiskItem
  icon: IconName
}

const stateStyle: Record<string, { cls: string; tile: string; pill: string; pillLabel: string; bar: string }> = {
  assessed:          { cls: 'border-emerald-200 bg-emerald-50', tile: 'bg-emerald-100 text-emerald-700', pill: 'risk-low',          pillLabel: 'Low',            bar: 'bg-emerald-500 w-1/4' },
  requires_review:   { cls: 'border-amber-200 bg-amber-50',     tile: 'bg-amber-100 text-amber-700',     pill: 'risk-moderate',     pillLabel: 'Needs review',   bar: 'bg-amber-500 w-2/4' },
  insufficient_data: { cls: 'border-slate-200 bg-slate-50',     tile: 'bg-slate-200 text-slate-500',     pill: 'risk-insufficient', pillLabel: 'Insufficient data', bar: 'bg-slate-400 w-0' },
  not_assessed:      { cls: 'border-slate-200 bg-slate-50',     tile: 'bg-slate-200 text-slate-500',     pill: 'risk-insufficient', pillLabel: 'Not assessed',   bar: 'bg-slate-400 w-0' },
}

const DiseaseRiskCard: FC<DiseaseRiskCardProps> = ({ disease, risk, icon }) => {
  const cfg = stateStyle[risk.state] ?? stateStyle['insufficient_data']
  // Legacy reports may carry a level without a state: show the stored level.
  const pillLabel = risk.level && risk.state === 'assessed'
    ? risk.level.replace(' Risk', '')
    : cfg.pillLabel
  return (
    <div className={`rounded-xl border-2 p-4 flex flex-col gap-3 ${cfg.cls}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`w-8 h-8 rounded-lg flex items-center justify-center ${cfg.tile}`}>
            <Icon name={icon} className="w-4 h-4" />
          </span>
          <span className="font-semibold text-slate-800 text-sm">{disease}</span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className={`${cfg.pill} whitespace-nowrap`}>{pillLabel}</span>
        </div>
      </div>

      {/* Assessment bar (only meaningful when assessed/review) */}
      <div className="h-1.5 bg-white/70 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${cfg.bar}`}/>
      </div>

      {/* Reason */}
      <p className="text-xs text-slate-600 leading-relaxed">{risk.reason}</p>

      {/* Supporting evidence */}
      {risk.evidence.length > 0 && (
        <ul className="text-xs text-slate-600 leading-relaxed list-disc pl-4 space-y-0.5">
          {risk.evidence.slice(0, 4).map((item, i) => <li key={i}>{item}</li>)}
        </ul>
      )}

      {/* Missing inputs */}
      {risk.missing.length > 0 && (
        <p className="text-xs text-slate-500 leading-relaxed">
          <span className="font-medium">Still needed: </span>
          {risk.missing.slice(0, 3).join(' ')}
        </p>
      )}

      {/* Method + decision-support footer */}
      <div className="mt-auto pt-1">
        {risk.method && (
          <p className="text-[11px] text-slate-400">Method: {risk.method}</p>
        )}
        {risk.guidance ? (
          <p className="text-[11px] text-slate-500 mt-0.5">{risk.guidance}</p>
        ) : (
          <p className="text-[11px] text-slate-500 mt-0.5">
            Preliminary decision support — a clinician makes the final decision.
          </p>
        )}
      </div>
    </div>
  )
}

export default DiseaseRiskCard
