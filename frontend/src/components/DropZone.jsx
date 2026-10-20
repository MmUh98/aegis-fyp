import { useState } from 'react'
import { FileImage, UploadCloud } from 'lucide-react'
import { IMAGE_TYPES, validateFile } from './fileTypes'

export default function DropZone({ onFile, label, hint, accepted = IMAGE_TYPES, fileName }) {
  const [dragging, setDragging] = useState(false)

  const handle = (file) => {
    if (file) onFile(file, validateFile(file, accepted))
  }

  return (
    <label
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault()
        setDragging(false)
        handle(event.dataTransfer.files?.[0])
      }}
      className={`group flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed p-8 text-center transition ${
        dragging
          ? 'border-cyan-300 bg-cyan-400/10'
          : 'border-slate-700 bg-slate-950/45 hover:border-cyan-400/60 hover:bg-slate-950/80'
      }`}
    >
      {fileName ? <FileImage className="mb-3 h-10 w-10 text-cyan-300" /> : <UploadCloud className="mb-3 h-10 w-10 text-slate-500 transition group-hover:text-cyan-300" />}
      <span className="text-sm font-semibold text-slate-200">{fileName || label}</span>
      <span className="mt-2 text-xs text-slate-500">{hint}</span>
      <input
        type="file"
        accept={accepted.join(',')}
        className="hidden"
        onChange={(event) => {
          handle(event.target.files?.[0])
          event.target.value = ''
        }}
      />
    </label>
  )
}
