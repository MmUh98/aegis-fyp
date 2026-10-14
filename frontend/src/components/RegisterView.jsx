import { useRef, useState } from 'react'
import { CheckCircle2, ExternalLink } from 'lucide-react'
import { getErrorMessage, registerMedia } from '../services/api'
import DropZone from './DropZone'

export default function RegisterView() {
  const [file, setFile] = useState(null)
  const [owns, setOwns] = useState(false)
  const [loading, setLoading] = useState(false)
  const [response, setResponse] = useState(null)
  const [error, setError] = useState(null)
  const requestId = useRef(0)

  const handleFile = (nextFile, validationError) => {
    requestId.current += 1
    setResponse(null)
    setLoading(false)
    setError(validationError)
    setFile(validationError ? null : nextFile)
  }

  const handleRegister = async () => {
    if (!file || !owns) return
    const id = ++requestId.current
    setLoading(true)
    setError(null)
    try {
      const nextResponse = await registerMedia(file)
      if (id === requestId.current) setResponse(nextResponse)
    } catch (requestError) {
      if (id === requestId.current) setError(getErrorMessage(requestError, 'Registration failed.'))
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }

  const safeLink = response?.explorerUrl?.startsWith('https://')

  return (
    <section className="mx-auto max-w-4xl px-4 py-8 sm:px-8 lg:py-16">
      <div className="panel space-y-6">
        <div className="max-w-2xl">
          <p className="eyebrow">Creator registration</p>
          <h1 className="mt-3 font-display text-4xl font-semibold tracking-tight text-slate-100">Register media provenance</h1>
          <p className="mt-4 text-sm leading-6 text-slate-400">Embeds a Falcon-512 signed manifest and anchors a perceptual fingerprint on Polygon Amoy. Registration proves you registered this file first. It does not prove the content is authentic.</p>
        </div>

        <DropZone onFile={handleFile} fileName={file?.name} accepted={['image/jpeg']} label="Choose the original JPEG" hint="JPEG only · up to 15 MB" />

        <label className="flex cursor-pointer items-start gap-3 text-sm text-slate-300">
          <input type="checkbox" checked={owns} onChange={(event) => setOwns(event.target.checked)} className="mt-1 h-4 w-4 accent-cyan-300" />
          <span>I am the creator or rights holder of this file.</span>
        </label>

        <button type="button" onClick={handleRegister} disabled={!file || !owns || loading} className="button-primary w-full">
          {loading ? 'Signing manifest and broadcasting transaction...' : 'Register on-chain'}
        </button>
        {error && <div role="alert" className="alert-error">{error}</div>}

        {response && (
          <div className="space-y-5 rounded-2xl border border-emerald-400/25 bg-emerald-400/5 p-5">
            <div className="flex items-center gap-2 font-semibold text-emerald-300"><CheckCircle2 className="h-5 w-5" /> Registered{response.blockNumber ? ` in block #${response.blockNumber}` : ''}</div>
            <div className="space-y-3 font-mono text-xs text-slate-300">
              <div><span className="text-slate-500">FALCON KEY HASH</span><p className="mt-1 break-all rounded-lg border border-slate-800 bg-slate-950 p-3">{response.falconKeyHash}</p></div>
              <div><span className="text-slate-500">MANIFEST HASH</span><p className="mt-1 break-all rounded-lg border border-slate-800 bg-slate-950 p-3">{response.manifestHash}</p></div>
            </div>
            {safeLink && <a href={response.explorerUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 text-sm text-cyan-300 hover:text-cyan-200"><span>View on PolygonScan</span><ExternalLink className="h-4 w-4" /></a>}
          </div>
        )}
      </div>
    </section>
  )
}
