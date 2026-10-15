/**
 * src/components/patient/AnalysisSummary.tsx
 * AI summary with disclaimer.
 */
import type { FC } from 'react'
import type { AnalysisResult } from '../../types/report.types'
import DiseaseRiskCard from './DiseaseRiskCard'
import ParameterTable from './ParameterTable'
import Icon from '../common/Icon'

interface AnalysisSummaryProps {
  analysis: AnalysisResult
}

const DISEASE_CONFIG = [
  { key: 'diabetes'       as const, label: 'Diabetes',               icon: 'droplet' as const },
  { key: 'ckd'            as const, label: 'Chronic Kidney Disease',  icon: 'activity' as const },
  { key: 'anemia'         as const, label: 'Anemia',                  icon: 'medicalCross' as const },
  { key: 'cardiovascular' as const, label: 'Cardiovascular Disease',  icon: 'heart' as const },
]

const AnalysisSummary: FC<AnalysisSummaryProps> = ({ analysis }) => {
  const analyzedDate = new Date(analysis.analyzed_at).toLocaleString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
  })

  return (
    <div className="flex flex-col gap-5">
      {/* Disclaimer banner */}
      <div className="alert-warning">
        <svg className="w-4 h-4 shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd"/>
        </svg>
        <span><strong>AI-Based Analysis Only.</strong> This is not a medical diagnosis. Risk cards show preliminary indicators for clinician review — a qualified doctor makes the final decision. Please consult a licensed healthcare professional before making any health decisions.</span>
      </div>

      {/* AI Summary */}
      <div className="card">
        <div className="flex items-center gap-2 mb-3">
          <span className="w-8 h-8 rounded-lg bg-indigo-100 text-indigo-700 flex items-center justify-center">
            <Icon name="sparkles" className="w-4 h-4" />
          </span>
          <h3 className="font-semibold text-slate-800">AI Summary</h3>
          <span className="text-xs text-slate-400 ml-auto">Generated {analyzedDate}</span>
        </div>
        <p className="text-sm text-slate-600 leading-relaxed">{analysis.summary}</p>
      </div>

      {/* Disease Risk Cards */}
      <div>
        <h3 className="font-semibold text-slate-800 mb-3">Disease Risk Assessment</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {DISEASE_CONFIG.map(({ key, label, icon }) => (
            <DiseaseRiskCard
              key={key}
              disease={label}
              risk={analysis.disease_risks[key]}
              icon={icon}
            />
          ))}
        </div>
      </div>

      {/* Parameters table */}
      {analysis.parameters.length > 0 && (
        <div className="card">
          <h3 className="font-semibold text-slate-800 mb-3">
            Extracted Parameters ({analysis.parameters.length})
          </h3>
          <ParameterTable parameters={analysis.parameters} />
        </div>
      )}
    </div>
  )
}

export default AnalysisSummary
