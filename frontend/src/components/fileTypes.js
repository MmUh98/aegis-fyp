export const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
export const VIDEO_TYPES = ['video/mp4', 'video/quicktime', 'video/webm']
export const MAX_IMAGE_BYTES = 15 * 1024 * 1024
export const MAX_VIDEO_BYTES = 50 * 1024 * 1024

const LABELS = {
  'image/jpeg': 'JPG',
  'image/png': 'PNG',
  'image/webp': 'WEBP',
  'video/mp4': 'MP4',
  'video/quicktime': 'MOV',
  'video/webm': 'WEBM',
}

const EXT_MIME = {
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.mp4': 'video/mp4',
  '.mov': 'video/quicktime',
  '.webm': 'video/webm',
}

export function resolveType(file) {
  if (file.type) return file.type
  const dot = file.name.lastIndexOf('.')
  return dot >= 0 ? EXT_MIME[file.name.slice(dot).toLowerCase()] || '' : ''
}

export function isVideoFile(file) {
  return VIDEO_TYPES.includes(resolveType(file))
}

export function validateFile(file, accepted = IMAGE_TYPES) {
  const type = resolveType(file)
  if (!accepted.includes(type)) return `Unsupported file type. Accepted: ${accepted.map((item) => LABELS[item] || item).join(', ')}.`
  const limit = VIDEO_TYPES.includes(type) ? MAX_VIDEO_BYTES : MAX_IMAGE_BYTES
  if (file.size > limit) return `File is too large. Maximum size is ${limit / (1024 * 1024)} MB.`
  return null
}
