export default function AudioTimeline({ windows, threshold, margin = 0.15, durationSeconds }) {
  if (!windows?.length) return null
  const duration = durationSeconds || windows[windows.length - 1].end
  const formatTime = (seconds) => `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
  return <div className="space-y-2"><div className="relative h-3 overflow-hidden rounded-full bg-slate-800">{windows.map((window) => { const high = threshold !== null && window.score >= threshold + margin; const uncertain = threshold !== null && window.score >= threshold - margin; const color = high ? 'bg-rose-300' : uncertain ? 'bg-amber-300' : 'bg-emerald-300'; return <span key={`${window.start}-${window.end}`} title={`${formatTime(window.start)}-${formatTime(window.end)}, score ${window.score.toFixed(2)}`} className={`absolute inset-y-0 rounded-sm ${color}`} style={{ left: `${(window.start / duration) * 100}%`, width: `${Math.max(((window.end - window.start) / duration) * 100, 0.5)}%` }} /> })}</div><p className="text-[11px] text-slate-500">Per-window audio scores. Gaps are silent sections.</p></div>
}
