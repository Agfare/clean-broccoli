import { useEffect, useRef, useState } from 'react'
import { filesApi } from '../api/files'
import { PreviewResponse } from '../types'

interface Props {
  fileId: string
  filename: string
  sourceLang?: string
  targetLang?: string
  onClose: () => void
}

export default function PreviewModal({ fileId, filename, sourceLang, targetLang, onClose }: Props) {
  const [data, setData]       = useState<PreviewResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  // Fetch on mount
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    filesApi
      .preview(fileId, { limit: 20, source_lang: sourceLang, target_lang: targetLang })
      .then((res) => { if (!cancelled) { setData(res.data); setLoading(false) } })
      .catch((err) => {
        if (!cancelled) {
          setError(err?.response?.data?.detail ?? err?.message ?? 'Failed to load preview')
          setLoading(false)
        }
      })
    return () => { cancelled = true }
  }, [fileId, sourceLang, targetLang])

  // Close on Escape key
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onClose])

  // Close on overlay click (not panel click)
  const handleOverlayClick = (e: React.MouseEvent) => {
    if (panelRef.current && !panelRef.current.contains(e.target as Node)) onClose()
  }

  const langPair = data
    ? `${data.source_lang} → ${data.target_lang}`
    : sourceLang && targetLang
      ? `${sourceLang} → ${targetLang}`
      : null

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      onClick={handleOverlayClick}
    >
      <div
        ref={panelRef}
        className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[80vh] flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 flex-shrink-0">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-gray-800 truncate">{filename}</h2>
            {langPair && (
              <p className="text-xs text-gray-400 mt-0.5">
                Language pair: <span className="font-mono text-gray-600">{langPair}</span>
                {data && (
                  <span className="ml-3">
                    Showing <span className="font-medium text-gray-700">{data.segments.length}</span> segment{data.segments.length !== 1 ? 's' : ''}
                  </span>
                )}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="ml-4 flex-shrink-0 text-gray-400 hover:text-gray-600 transition"
            aria-label="Close preview"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          {loading && (
            <div className="flex items-center justify-center py-16 gap-3 text-gray-400">
              <span className="w-5 h-5 border-2 border-gray-300 border-t-indigo-500 rounded-full animate-spin" />
              <span className="text-sm">Loading preview…</span>
            </div>
          )}

          {error && (
            <div className="m-6 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          {data && !loading && (
            <>
              {/* Warnings */}
              {data.warnings.length > 0 && (
                <div className="mx-6 mt-4 bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-3">
                  <p className="text-xs font-medium text-yellow-800 mb-1">Parse warnings</p>
                  <ul className="space-y-0.5">
                    {data.warnings.map((w, i) => (
                      <li key={i} className="text-xs text-yellow-700">{w}</li>
                    ))}
                  </ul>
                </div>
              )}

              {data.segments.length === 0 ? (
                <div className="py-12 text-center text-sm text-gray-400">
                  No segments could be read from this file.
                </div>
              ) : (
                <table className="w-full text-sm border-collapse">
                  <thead className="sticky top-0 bg-gray-50 z-10">
                    <tr>
                      <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide w-20 border-b border-gray-200">
                        ID
                      </th>
                      <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide border-b border-gray-200">
                        Source ({data.source_lang})
                      </th>
                      <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide border-b border-gray-200">
                        Target ({data.target_lang})
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.segments.map((seg, i) => (
                      <tr
                        key={seg.id}
                        className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}
                      >
                        <td className="px-4 py-2.5 text-xs text-gray-400 font-mono align-top border-b border-gray-100">
                          {seg.id}
                        </td>
                        <td className="px-4 py-2.5 text-gray-700 align-top border-b border-gray-100 max-w-xs">
                          <span className="line-clamp-3">{seg.source || <em className="text-gray-300">empty</em>}</span>
                        </td>
                        <td className="px-4 py-2.5 text-gray-700 align-top border-b border-gray-100 max-w-xs">
                          <span className="line-clamp-3">{seg.target || <em className="text-gray-300">empty</em>}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end px-6 py-3 border-t border-gray-200 flex-shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-md transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
