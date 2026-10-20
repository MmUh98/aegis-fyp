import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Cpu, Database, Eye, KeyRound, Mic, MinusCircle, ShieldCheck, XCircle } from 'lucide-react'
import { getErrorMessage, verifyMedia } from '../services/api'
import DropZone from './DropZone'
import { IMAGE_TYPES, VIDEO_TYPES, isVideoFile } from './fileTypes'
import VerdictBadge from './VerdictBadge'

const ACCEPTED = [...IMAGE_TYPES, ...VIDEO_TYPES]

function ModalityRow({ icon: Icon, label, unit, modality }) {
  if (modality.status === 'ran') {
    const count = modality.frames ?? modality.chunks
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-2 font-mono text-[10px] tracking-[0.12em] text-slate-500"><Icon className="h-4 w-4 text-purple-300" />{label}</div>
        <p className="text-sm font-semibold text-slate-200">Score {modality.score.toFixed(2)}{modality.threshold !== null && <span className="font-normal text-slate-500"> · threshold {modality.threshold.toFixed(2)}</span>}</p>
        <div className="h-1.5 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-purple-300" style={{ width: `${Math.round(modality.score * 100)}%` }} /></div>
        {count !== null && count !== undefined && <p className="text-xs text-slate-500">{count} {unit} analyzed</p>}
      </div>
    )
  }
  if (modality.status === 'not_applicable') return <span className="status-muted">Not applicable</span>
  if (modality.status === 'no_audio_track') return <span className="status-muted">No audio track</span>
  if (modality.status === 'no_usable_audio') return <span className="status-muted">No usable speech (silent or too short)</span>
  if (modality.status === 'disabled') return <span className="status-warn"><AlertTriangle /> Detector offline</span>
  return <span className="status-warn"><AlertTriangle /> Analysis failed</span>
}

export default function VerifyView() {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const requestId = useRef(0)
  const abortRef = useRef(null)

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview)
  }, [preview])

  useEffect(() => () => abortRef.current?.abort(), [])

  const handleFile = (nextFile, validationError) => {
    requestId.current += 1
    abortRef.current?.abort()
    setResult(null)
    setLoading(false)
    setProgress(0)
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
    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true)
    setProgress(0)
    setError(null)
    try {
      const nextResult = await verifyMedia(file, { onProgress: setProgress, signal: controller.signal })
      if (id === requestId.current) setResult(nextResult)
    } catch (requestError) {
      if (id === requestId.current && requestError?.code !== 'ERR_CANCELED') setError(getErrorMessage(requestError, 'Verification service failed.'))
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }

  const video = file ? isVideoFile(file) : false
  const buttonLabel = !loading ? 'Verify provenance' : progress < 100 ? `Uploading ${progress}%` : video ? 'Analyzing frames and audio...' : 'Running verification...'

  return (
    <section className="mx-auto grid max-w-7xl grid-cols-1 gap-6 px-4 py-8 sm:px-8 lg:grid-cols-[minmax(300px,0.8fr)_minmax(0,1.2fr)] lg:py-12">
      <div className="space-y-5">
        <div className="max-w-xl"><p className="eyebrow">Three-layer media analysis</p><h1 className="mt-3 font-display text-4xl font-semibold tracking-tight text-slate-100 sm:text-5xl">See what the file can prove.</h1><p className="mt-4 text-sm leading-6 text-slate-400">Aegis checks embedded provenance first, then the Polygon registry, and only uses visual and audio detectors when those signals are unavailable.</p></div>
        <div className="panel space-y-4">
          <div><p className="eyebrow">Input asset</p><h2 className="mt-2 text-lg font-semibold text-slate-100">Verify provenance</h2></div>
          <DropZone onFile={handleFile} accepted={ACCEPTED} fileName={file?.name} label="Choose or drop an image or video" hint="Images: JPG, PNG, WEBP up to 15 MB · Videos: MP4, MOV, WEBM up to 50 MB and 2 minutes" />
          {preview && <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950">{video ? <video src={preview} controls muted playsInline className="h-48 w-full object-cover" /> : <img src={preview} alt="Selected media preview" className="h-48 w-full object-cover" />}</div>}
          <button type="button" onClick={handleVerify} disabled={!file || loading} className="button-primary w-full">{buttonLabel}</button>
          {error && <div role="alert" className="alert-error">{error}</div>}
        </div>
      </div>

      <div className="min-h-[28rem]">
        {result ? <div className="panel space-y-6">
          <div className="space-y-2 border-b border-slate-800 pb-5"><p className="eyebrow">Assessment</p><VerdictBadge verdict={result.verdict} />{result.triggeredBy.length > 0 && <p className="text-xs text-slate-400">Flagged by: {result.triggeredBy.join(' and ')}. Either detector can flag the file.</p>}</div>
          {result.reason && <p className="rounded-xl border border-slate-800 bg-slate-950/75 p-4 text-sm leading-6 text-slate-300">{result.reason}</p>}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <article className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4"><div className="mb-3 flex items-center gap-2 font-mono text-[10px] tracking-[0.16em] text-slate-500"><KeyRound className="h-4 w-4 text-cyan-300" />LAYER 1 · C2PA</div>{result.c2pa === 'VALID' ? <span className="status-good"><CheckCircle2 /> Valid</span> : result.c2pa === 'TAMPERED' ? <span className="status-bad"><XCircle /> Tampered</span> : <span className="status-muted"><MinusCircle /> Absent</span>}</article>
            <article className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4"><div className="mb-3 flex items-center gap-2 font-mono text-[10px] tracking-[0.16em] text-slate-500"><Database className="h-4 w-4 text-cyan-300" />LAYER 2 · REGISTRY</div>{!result.registryApplicable ? <span className="status-muted"><MinusCircle /> Not applicable to video</span> : result.onChainMatch ? <span className="status-good"><CheckCircle2 /> Registered on-chain</span> : <span className="status-muted"><MinusCircle /> Not registered</span>}</article>
            <article className="space-y-3 rounded-2xl border border-slate-800 bg-slate-950/70 p-4"><div className="flex items-center gap-2 font-mono text-[10px] tracking-[0.16em] text-slate-500"><Cpu className="h-4 w-4 text-purple-300" />LAYER 3 · AI DETECTORS</div>{result.layer3 === 'ran' && <><ModalityRow icon={Eye} label="Visual · SigLIP-2" unit="frames" modality={result.visual} />{result.mediaType === 'video' && <ModalityRow icon={Mic} label="Audio · Wav2Vec2" unit="chunks" modality={result.audio} />}<p className="text-xs leading-5 text-slate-500">Uncalibrated model outputs, not proof.{result.mediaType === 'video' && ' The audio detector targets synthetic speech only; it does not detect lip-sync or face-swap manipulation.'}</p></>}{result.layer3 === 'not_needed' && <div className="text-sm text-slate-400">Not needed (resolved by Layer 1/2)</div>}{result.layer3 === 'error' && <span className="status-warn"><AlertTriangle /> Unavailable (detector error)</span>}</article>
          </div>
        </div> : <div className="flex h-full min-h-[28rem] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-800 bg-slate-900/25 p-10 text-center"><ShieldCheck className="h-16 w-16 text-cyan-300/20" /><p className="mt-5 max-w-sm text-sm leading-6 text-slate-500">Upload an image or video to see the evidence hierarchy and detector breakdown.</p></div>}
      </div>
    </section>
  )
}
