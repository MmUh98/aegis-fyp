import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Cpu, Database, FileSearch, KeyRound, MinusCircle, ShieldCheck, XCircle } from 'lucide-react'
import { getErrorMessage, verifyMedia } from '../services/api'
import DropZone from './DropZone'
import VerdictBadge from './VerdictBadge'

function LayerCard({ icon: Icon, label, children }) {
  return (
    <article className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
      <div className="mb-3 flex items-center gap-2 font-mono text-[10px] tracking-[0.16em] text-slate-500">
        <Icon className="h-4 w-4 text-cyan-300" />
        <span>{label}</span>
      </div>
      {children}
    </article>
  )
}

export default function VerifyView() {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const requestId = useRef(0)

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview)
  }, [preview])

  const handleFile = (nextFile, validationError) => {
    requestId.current += 1
    setResult(null)
    setLoading(false)
    setError(validationError)
    if (validationError) {
      setFile(null)
      setPreview(null)
      return
    }
    setFile(nextFile)
    setPreview(URL.createObjectURL(nextFile))
  }

  const handleVerify = async () => {
    if (!file) return
    const id = ++requestId.current
    setLoading(true)
    setError(null)
    try {
      const nextResult = await verifyMedia(file)
      if (id === requestId.current) setResult(nextResult)
    } catch (requestError) {
      if (id === requestId.current) setError(getErrorMessage(requestError, 'Verification service failed.'))
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }

  const renderC2pa = () => {
    if (result.c2pa === 'VALID') return <span className="status-good"><CheckCircle2 /> Valid</span>
    if (result.c2pa === 'TAMPERED') return <span className="status-bad"><XCircle /> Tampered</span>
    return <span className="status-muted"><MinusCircle /> Absent</span>
  }

  return (
    <section className="mx-auto grid max-w-7xl grid-cols-1 gap-6 px-4 py-8 sm:px-8 lg:grid-cols-[minmax(300px,0.8fr)_minmax(0,1.2fr)] lg:py-12">
      <div className="space-y-5">
        <div className="max-w-xl">
          <p className="eyebrow">Three-layer media analysis</p>
          <h1 className="mt-3 font-display text-4xl font-semibold tracking-tight text-slate-100 sm:text-5xl">See what the file can prove.</h1>
          <p className="mt-4 max-w-lg text-sm leading-6 text-slate-400">Aegis checks embedded provenance first, then the Polygon registry, and only uses the fine-tuned detector when those signals are unavailable.</p>
        </div>

        <div className="panel space-y-4">
          <div>
            <p className="font-mono text-[10px] tracking-[0.16em] text-slate-500">INPUT ASSET</p>
            <h2 className="mt-2 text-lg font-semibold text-slate-100">Verify provenance</h2>
          </div>
          <DropZone onFile={handleFile} fileName={file?.name} label="Choose or drop an image" hint="JPG, PNG, or WEBP · up to 15 MB" />
          {preview && <img src={preview} alt="Selected media preview" className="h-48 w-full rounded-xl border border-slate-800 object-cover" />}
          <button type="button" onClick={handleVerify} disabled={!file || loading} className="button-primary w-full">
            {loading ? 'Running verification...' : 'Verify provenance'}
          </button>
          {error && <div role="alert" className="alert-error">{error}</div>}
        </div>
      </div>

      <div className="min-h-[28rem]">
        {result ? (
          <div className="panel space-y-6">
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-800 pb-5">
              <div>
                <p className="eyebrow">Assessment</p>
                <h2 className="mt-2 text-2xl font-semibold text-slate-100">Verification result</h2>
              </div>
              <VerdictBadge verdict={result.verdict} />
            </div>
            {result.reason && <p className="rounded-xl border border-slate-800 bg-slate-950/75 p-4 text-sm leading-6 text-slate-300">{result.reason}</p>}

            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <LayerCard icon={KeyRound} label="LAYER 1 · C2PA">{renderC2pa()}</LayerCard>
              <LayerCard icon={Database} label="LAYER 2 · REGISTRY">
                {result.onChainMatch ? <span className="status-good"><CheckCircle2 /> Registered on-chain</span> : <span className="status-muted"><MinusCircle /> Not registered</span>}
              </LayerCard>
              <LayerCard icon={Cpu} label="LAYER 3 · DETECTOR">
                {result.layer3 === 'ran' && (
                  <div className="space-y-2">
                    <p className="text-sm font-semibold text-slate-200">Detector score {result.aiScore.toFixed(2)}{result.threshold !== null && <span className="font-normal text-slate-500"> · threshold {result.threshold.toFixed(2)}</span>}</p>
                    <div className="h-1.5 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-cyan-300" style={{ width: `${Math.round(result.aiScore * 100)}%` }} /></div>
                    <p className="text-xs leading-5 text-slate-500">Uncalibrated model output, not proof.</p>
                  </div>
                )}
                {result.layer3 === 'not_needed' && <span className="status-muted"><FileSearch /> Not needed (resolved by Layer 1/2)</span>}
                {result.layer3 === 'error' && <span className="status-warn"><AlertTriangle /> Unavailable (detector error)</span>}
              </LayerCard>
            </div>
            {result.detectorReason && result.layer3 === 'ran' && <p className="text-xs text-slate-500">{result.detectorReason}</p>}
          </div>
        ) : (
          <div className="flex h-full min-h-[28rem] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-800 bg-slate-900/25 p-10 text-center">
            <ShieldCheck className="h-16 w-16 text-cyan-300/20" />
            <p className="mt-5 max-w-sm text-sm leading-6 text-slate-500">Upload an image to see the evidence hierarchy and the final assessment.</p>
          </div>
        )}
      </div>
    </section>
  )
}
