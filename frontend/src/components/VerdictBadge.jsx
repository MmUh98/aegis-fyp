import { FileSearch, HelpCircle, Scale, ShieldAlert, ShieldCheck, ShieldX } from 'lucide-react'

const CONFIGS = {
  VERIFIED_AUTHENTIC: { color: 'bg-emerald-400/10 text-emerald-300 border-emerald-400/25', icon: ShieldCheck, label: 'PROVENANCE VERIFIED' },
  SIGNED_UNVERIFIED_SIGNER: { color: 'bg-amber-400/10 text-amber-300 border-amber-400/25', icon: ShieldAlert, label: 'SIGNED, SIGNER UNVERIFIED' },
  TAMPERED: { color: 'bg-rose-400/10 text-rose-300 border-rose-400/25', icon: ShieldX, label: 'MANIFEST TAMPERED' },
  PROVENANCE_STRIPPED: { color: 'bg-sky-400/10 text-sky-300 border-sky-400/25', icon: FileSearch, label: 'PROVENANCE STRIPPED' },
  LIKELY_REAL: { color: 'bg-emerald-400/10 text-emerald-300 border-emerald-400/25', icon: ShieldCheck, label: 'DETECTOR: LEANS REAL' },
  LIKELY_FAKE: { color: 'bg-rose-400/10 text-rose-300 border-rose-400/25', icon: ShieldX, label: 'DETECTOR: LEANS SYNTHETIC' },
  UNCERTAIN: { color: 'bg-amber-400/10 text-amber-300 border-amber-400/25', icon: Scale, label: 'DETECTOR: UNCERTAIN' },
  INCONCLUSIVE: { color: 'bg-slate-400/10 text-slate-300 border-slate-400/25', icon: HelpCircle, label: 'INCONCLUSIVE' },
}

export default function VerdictBadge({ verdict }) {
  const config = CONFIGS[verdict] || CONFIGS.INCONCLUSIVE
  const Icon = config.icon
  return (
    <div className={`inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-bold tracking-[0.12em] ${config.color}`}>
      <Icon className="h-4 w-4" />
      <span>{config.label}</span>
    </div>
  )
}
