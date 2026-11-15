/** src/types/report.types.ts */
export type ReportStatus = 'uploaded' | 'extracting' | 'extracted' | 'analyzing' | 'analyzed' | 'failed'
export type RiskLevel = 'Low Risk' | 'Moderate Risk' | 'High Risk' | 'Insufficient Data'
export type AssessmentState = 'assessed' | 'insufficient_data' | 'not_assessed' | 'requires_review'
export type ParamStatus = 'Normal' | 'Low' | 'High' | 'Critical' | 'Unknown'

export interface MedicalParameter {
  name: string
  value: string | number
  unit: string
  status: ParamStatus
  reference_range?: string
  report_flag?: string
  flag_mismatch?: boolean
}

export interface DiseaseRiskItem {
  level: RiskLevel | null
  reason: string
  state: AssessmentState
  evidence: string[]
  missing: string[]
  method?: string
  guidance: string
}

export interface DiseaseRisks {
  diabetes: DiseaseRiskItem
  ckd: DiseaseRiskItem
  anemia: DiseaseRiskItem
  cardiovascular: DiseaseRiskItem
}

export interface AnalysisResult {
  report_id: string
  summary: string
  parameters: MedicalParameter[]
  disease_risks: DiseaseRisks
  analyzed_at: string
}

export interface ReportUploadResponse {
  id: string
  original_filename: string
  status: ReportStatus
  uploaded_at: string
}

export interface ReportListItem {
  id: string
  original_filename: string
  status: ReportStatus
  uploaded_at: string
  analyzed_at?: string
  has_analysis: boolean
}

export interface ReportDetail {
  id: string
  original_filename: string
  status: ReportStatus
  extracted_text?: string
  uploaded_at: string
  analyzed_at?: string
  error_message?: string
  has_analysis: boolean
}
