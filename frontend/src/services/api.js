import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
const client = axios.create({ baseURL: API_BASE_URL, timeout: 120000 })

export function getErrorMessage(err, fallback = 'Something went wrong.') {
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
  const aiScore = typeof data.ai_score === 'number' ? data.ai_score : null
  const c2pa = data.c2pa_status ?? 'ABSENT'
  const onChainMatch = Boolean(data.on_chain_match)
  const resolvedEarlier = c2pa !== 'ABSENT' || onChainMatch

  let layer3 = 'error'
  if (aiScore !== null) layer3 = 'ran'
  else if (resolvedEarlier) layer3 = 'not_needed'

  return {
    verdict: data.verdict ?? 'INCONCLUSIVE',
    reason: data.reason ?? '',
    c2pa,
    onChainMatch,
    aiScore,
    threshold: typeof data.threshold_used === 'number' ? data.threshold_used : null,
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

export async function verifyMedia(file) {
  const formData = new FormData()
  formData.append('file', file)
  const response = await client.post('/api/v1/verify', formData)
  return normalizeVerifyResponse(response.data)
}

export async function registerMedia(file) {
  const formData = new FormData()
  formData.append('file', file)
  const response = await client.post('/api/v1/register', formData)
  return normalizeRegisterResponse(response.data)
}
