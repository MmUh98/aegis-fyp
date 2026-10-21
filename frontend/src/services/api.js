import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
const client = axios.create({ baseURL: API_BASE_URL, timeout: 120000 })

export function getErrorMessage(err, fallback = 'Something went wrong.') {
  if (err?.code === 'ERR_CANCELED') return ''
  if (!err.response) {
    return err.code === 'ECONNABORTED'
      ? 'The request timed out. Please try again.'
      : 'Cannot reach the Aegis server. Is the backend running?'
  }
  const detail = err.response.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg || JSON.stringify(item)).join('; ')
  }
  if (detail && typeof detail === 'object') return detail.message || JSON.stringify(detail)
  return `${fallback} (HTTP ${err.response.status})`
}

export function normalizeVerifyResponse(data) {
  const num = (value) => (typeof value === 'number' ? value : null)
  const normalizeModality = (raw, fallbackScore = null, fallbackThreshold = null) => {
    const score = num(raw?.score ?? fallbackScore)
    return {
      status: raw?.status ?? (score !== null ? 'ran' : 'error'),
      verdict: raw?.verdict ?? null,
      score,
      threshold: num(raw?.threshold_used ?? fallbackThreshold),
      frames: num(raw?.frames_analyzed),
      chunks: num(raw?.chunks_analyzed),
      windows: Array.isArray(raw?.windows) ? raw.windows.filter((window) => typeof window?.start === 'number' && typeof window?.end === 'number' && typeof window?.score === 'number') : [],
      modelLabel: raw?.model_label ?? null,
      calibration: raw?.calibration_status ?? null,
      uncertainMargin: num(raw?.uncertain_margin),
    }
  }

  const c2pa = data.c2pa_status ?? 'ABSENT'
  const onChainMatch = Boolean(data.on_chain_match)
  const resolvedEarlier = c2pa !== 'ABSENT' || onChainMatch
  const visual = normalizeModality(data.visual, data.ai_score, data.threshold_used)
  const audio = normalizeModality(data.audio ?? { status: 'not_applicable' })
  const detectorsPresent = Boolean(data.visual || data.audio) || visual.score !== null

  let layer3 = 'error'
  if (detectorsPresent) layer3 = 'ran'
  else if (resolvedEarlier) layer3 = 'not_needed'

  return {
    verdict: data.verdict ?? 'INCONCLUSIVE',
    reason: data.reason ?? '',
    c2pa,
    onChainMatch,
    registryApplicable: data.registry_status !== 'NOT_APPLICABLE',
    mediaType: data.media_type ?? 'image',
    visual,
    audio,
    triggeredBy: Array.isArray(data.triggered_by) ? data.triggered_by : [],
    diagnosis: data.diagnosis ?? null,
    audioAssessed: Boolean(data.audio_assessed),
    durationSeconds: typeof data.media_duration_seconds === 'number' ? data.media_duration_seconds : null,
    detectorReason: data.detector_reason ?? '',
    layer3,
  }
}

export function normalizeRegisterResponse(data) {
  return {
    blockNumber: data.block_number ?? null,
    falconKeyHash: data.falcon_key_hash ?? '',
    manifestHash: data.manifest_hash ?? '',
    explorerUrl: data.explorer_url ?? '',
    message: data.message ?? '',
  }
}

export async function verifyMedia(file, { onProgress, signal } = {}) {
  const formData = new FormData()
  formData.append('file', file)
  const response = await client.post('/api/v1/verify', formData, {
    timeout: 180000,
    signal,
    onUploadProgress: (event) => {
      if (onProgress && event.total) onProgress(Math.round((event.loaded * 100) / event.total))
    },
  })
  return normalizeVerifyResponse(response.data)
}

export async function registerMedia(file) {
  const formData = new FormData()
  formData.append('file', file)
  const response = await client.post('/api/v1/register', formData)
  return normalizeRegisterResponse(response.data)
}
