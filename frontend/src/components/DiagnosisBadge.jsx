import { Eye, Mic, ShieldCheck, ShieldX } from 'lucide-react'

const CONFIGS = {
  Authentic: { color: 'bg-emerald-400/10 text-emerald-300 border-emerald-400/25', icon: ShieldCheck, label: 'AUTHENTIC', subtitle: 'No manipulation detected by the AI detectors. This is not a provenance guarantee.' },
  'Audio Substitution': { color: 'bg-purple-400/10 text-purple-300 border-purple-400/25', icon: Mic, label: 'AUDIO SUBSTITUTION', subtitle: 'The visuals look genuine, but the speech sounds synthetic or replaced.' },
  'AI Visual': { color: 'bg-orange-400/10 text-orange-300 border-orange-400/25', icon: Eye, label: 'AI VISUAL', subtitle: 'The visuals look synthetic. The audio sounds genuine or was not assessed.' },
  'Full Deepfake': { color: 'bg-rose-400/10 text-rose-300 border-rose-400/25', icon: ShieldX, label: 'FULL DEEPFAKE', subtitle: 'Both the visuals and the speech look synthetic.' },
}

export default function DiagnosisBadge({ diagnosis, audioAssessed }) {
  const config = CONFIGS[diagnosis]
  if (!config) return null
  const Icon = config.icon
  const notAssessed = !audioAssessed && diagnosis !== 'Audio Substitution' && diagnosis !== 'Full Deepfake'
  return <div className="space-y-2"><div className={`inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-bold tracking-[0.12em] ${config.color}`}><Icon className="h-4 w-4" /><span>{config.label}</span></div><p className="text-xs leading-5 text-slate-400">{config.subtitle}{notAssessed ? ' Audio was not assessed.' : ''}</p></div>
}
