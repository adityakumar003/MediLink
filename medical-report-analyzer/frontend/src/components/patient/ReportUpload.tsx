/**
 * src/components/patient/ReportUpload.tsx
 * File picker + upload + trigger analysis flow.
 */
import { useState, useRef, type FC } from 'react'
import { uploadReport, triggerAnalysis } from '../../services/reportService'
import type { ReportUploadResponse } from '../../types/report.types'
import LoadingSpinner from '../common/LoadingSpinner'
import Icon from '../common/Icon'

interface ReportUploadProps {
  onUploaded?: (report: ReportUploadResponse & { analyzed?: boolean }) => void
}

type Stage = 'idle' | 'uploading' | 'uploaded' | 'analyzing' | 'done' | 'error'

const ReportUpload: FC<ReportUploadProps> = ({ onUploaded }) => {
  const [stage, setStage] = useState<Stage>('idle')
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const allowedTypes = new Set(['application/pdf', 'image/jpeg', 'image/png', 'image/jpg'])

  const handleFile = (f: File) => {
    const ext = f.name.split('.').pop()?.toLowerCase()
    const allowedExt = ext === 'pdf' || ext === 'jpg' || ext === 'jpeg' || ext === 'png'
    if (!allowedTypes.has(f.type) && !allowedExt) {
      setError('Only PDF and image files (JPG, JPEG, PNG) are accepted.')
      return
    }
    if (f.size > 10 * 1024 * 1024) {
      setError('File size must be under 10 MB.')
      return
    }
    setFile(f)
    setError('')
    setStage('idle')
  }

  const handleUpload = async () => {
    if (!file) return
    setStage('uploading')
    setError('')
    try {
      const res = await uploadReport(file)
      setStage('uploaded')
      // Immediately trigger analysis
      setStage('analyzing')
      await triggerAnalysis(res.id)
      setStage('done')
      onUploaded?.({ ...res, analyzed: true })
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg || 'Upload or analysis failed. Please try again.')
      setStage('error')
    }
  }

  const reset = () => {
    setStage('idle'); setFile(null); setError('')
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <div className="card">
      <h3 className="flex items-center gap-2 font-semibold text-slate-800 mb-1">
        <span className="w-8 h-8 rounded-lg bg-blue-100 text-blue-700 flex items-center justify-center">
          <Icon name="file" className="w-4 h-4" />
        </span>
        Upload Medical Report
      </h3>
      <p className="text-sm text-slate-500 mb-4">Upload a PDF or image lab report to get an AI-powered analysis.</p>

      {/* Drop zone */}
      {stage === 'idle' && !file && (
        <div
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={e => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f) }}
          onClick={() => inputRef.current?.click()}
          className={`dropzone ${dragOver ? 'drag-over' : ''}`}>
          <span className="stat-tile !w-14 !h-14">
            <Icon name="upload" className="w-6 h-6" />
          </span>
          <div className="text-center">
            <p className="font-semibold text-slate-800">Drag & drop your lab report</p>
            <p className="text-sm text-slate-400 mt-1">or click to browse files</p>
          </div>
          <input ref={inputRef} type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" className="sr-only"
            onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }} />
        </div>
      )}

      {/* File selected — show info + upload button */}
      {file && stage === 'idle' && (
        <div className="mt-3 flex items-center gap-3 p-3 bg-slate-50 rounded-lg border border-slate-200">
          <svg className="w-8 h-8 text-red-500 shrink-0" fill="currentColor" viewBox="0 0 24 24">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6ZM14 3.5 18.5 8H14V3.5Z"/>
          </svg>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-700 truncate">{file.name}</p>
            <p className="text-xs text-slate-400">{(file.size / 1024).toFixed(0)} KB</p>
          </div>
          <button onClick={reset} className="btn-ghost btn-sm text-slate-400" title="Remove">✕</button>
          <button onClick={handleUpload} className="btn-primary btn-sm">Upload & Analyse</button>
        </div>
      )}

      {/* Status messages */}
      {stage === 'uploading' && (
        <div className="mt-4 flex items-center gap-3 text-sm text-slate-600">
          <LoadingSpinner size="sm" /> Uploading report…
        </div>
      )}
      {stage === 'analyzing' && (
        <div className="mt-4 flex items-center gap-3 text-sm text-slate-600">
          <LoadingSpinner size="sm" /> Running AI analysis (hosted model may take a minute if it is waking up)…
        </div>
      )}
      {stage === 'done' && (
        <div className="alert-success mt-4">
          <Icon name="checkCircle" className="w-4 h-4 shrink-0" />
          Analysis complete! Scroll down to view your results.
          <button onClick={reset} className="ml-auto text-xs underline">Upload another</button>
        </div>
      )}
      {(stage === 'error' || error) && (
        <div className="alert-error mt-4">
          {error}
          {stage === 'error' && <button onClick={reset} className="ml-2 underline text-xs">Try again</button>}
        </div>
      )}
    </div>
  )
}

export default ReportUpload
