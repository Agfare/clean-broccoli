import { useState } from 'react'
import { JobResults, Job } from '../types'

interface Props {
  results: JobResults | null
  job: Job | null
}

// ── Helpers ──────────────────────────────────────────────────────────────────

type DetailedType = 'tmx' | 'clean_xls' | 'qa_xls' | 'html' | 'duplicates' | 'untranslated' | 'other'

function getDetailedType(filename: string): DetailedType {
  const name = filename.toLowerCase()
  // Match the type keyword just before the _SRCLANG_TGTLANG.EXT suffix,
  // preceded by either the start of the string or an underscore (prefix boundary).
  // This works for both plain names (clean_en_de.tmx) and prefixed ones (proj_clean_en_de.tmx).
  const m = name.match(/(?:^|_)(clean|qa|duplicates|untranslated)_[a-z]{2,3}_[a-z]{2,3}\.[a-z]+$/)
  const keyword = m?.[1]

  if (name.endsWith('.tmx')) {
    if (keyword === 'duplicates')   return 'duplicates'
    if (keyword === 'untranslated') return 'untranslated'
    return 'tmx'
  }
  if (name.endsWith('.xlsx') || name.endsWith('.xls')) {
    if (keyword === 'qa')           return 'qa_xls'
    if (keyword === 'duplicates')   return 'duplicates'
    if (keyword === 'untranslated') return 'untranslated'
    return 'clean_xls'
  }
  if (name.endsWith('.html') || name.endsWith('.htm')) return 'html'
  return 'other'
}

const TYPE_LABELS: Record<DetailedType, string> = {
  tmx:          'TMX',
  clean_xls:    'Clean XLS',
  qa_xls:       'QA XLS',
  html:         'HTML Report',
  duplicates:   'Duplicates',
  untranslated: 'Untranslated',
  other:        'Other',
}

const TYPE_ICONS: Record<DetailedType, string> = {
  tmx:          '📄',
  clean_xls:    '📊',
  qa_xls:       '📋',
  html:         '📈',
  duplicates:   '🔁',
  untranslated: '⚠️',
  other:        '📁',
}

/** Extract "en → de" from filenames like clean_en_de.tmx */
function extractLangPair(filename: string): string | null {
  const match = filename.match(/_([a-z]{2,3})_([a-z]{2,3})\.[a-z]+$/i)
  if (match) return `${match[1].toLowerCase()} → ${match[2].toLowerCase()}`
  return null
}

function isHtmlFile(filename: string): boolean {
  return filename.toLowerCase().endsWith('.html') || filename.toLowerCase().endsWith('.htm')
}

// ── Filter pill ───────────────────────────────────────────────────────────────

function Pill({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1 rounded-full text-xs font-medium border transition whitespace-nowrap ${
        active
          ? 'bg-indigo-600 text-white border-indigo-600'
          : 'bg-white text-gray-600 border-gray-300 hover:border-indigo-400 hover:text-indigo-600'
      }`}
    >
      {label}
    </button>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ResultsPanel({ results, job }: Props) {
  const [activeLang, setActiveLang] = useState<string | null>(null)
  const [activeType, setActiveType] = useState<DetailedType | null>(null)

  if (!results || results.outputs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <svg
          className="w-12 h-12 text-gray-300 mb-3"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
        <p className="text-sm text-gray-400">No output files available</p>
      </div>
    )
  }

  // Collect distinct language pairs and file types from all outputs
  const langPairs = [...new Set(
    results.outputs
      .map((o) => extractLangPair(o.filename))
      .filter((l): l is string => l !== null)
  )].sort()

  const fileTypes = [...new Set(
    results.outputs.map((o) => getDetailedType(o.filename))
  )].sort()

  // Apply filters
  const visible = results.outputs.filter((o) => {
    if (activeLang !== null && extractLangPair(o.filename) !== activeLang) return false
    if (activeType !== null && getDetailedType(o.filename) !== activeType) return false
    return true
  })

  const showLangFilter = langPairs.length > 1
  const showTypeFilter = fileTypes.length > 1

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-semibold text-gray-800">
          Results
          {(activeLang || activeType) && (
            <span className="ml-2 text-xs font-normal text-gray-400">
              {visible.length} of {results.outputs.length} files
            </span>
          )}
        </h2>
        {job && (
          <div className="text-xs text-gray-500">
            Job{' '}
            <span className="font-mono text-gray-700">{job.id.slice(0, 8)}…</span>
          </div>
        )}
      </div>

      {/* Filters */}
      {(showLangFilter || showTypeFilter) && (
        <div className="space-y-2 mb-4">
          {/* Language filter */}
          {showLangFilter && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-gray-400 w-16 flex-shrink-0">Language</span>
              <Pill
                label="All"
                active={activeLang === null}
                onClick={() => setActiveLang(null)}
              />
              {langPairs.map((pair) => (
                <Pill
                  key={pair}
                  label={pair}
                  active={activeLang === pair}
                  onClick={() => setActiveLang(activeLang === pair ? null : pair)}
                />
              ))}
            </div>
          )}

          {/* File type filter */}
          {showTypeFilter && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-gray-400 w-16 flex-shrink-0">Type</span>
              <Pill
                label="All"
                active={activeType === null}
                onClick={() => setActiveType(null)}
              />
              {fileTypes.map((type) => (
                <Pill
                  key={type}
                  label={TYPE_LABELS[type]}
                  active={activeType === type}
                  onClick={() => setActiveType(activeType === type ? null : type)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* File list */}
      {visible.length === 0 ? (
        <div className="py-8 text-center text-sm text-gray-400">
          No files match the selected filters.{' '}
          <button
            className="text-indigo-500 hover:underline"
            onClick={() => { setActiveLang(null); setActiveType(null) }}
          >
            Clear filters
          </button>
        </div>
      ) : (
        <ul className="space-y-2">
          {visible.map((output) => {
            const detailedType = getDetailedType(output.filename)
            const html = isHtmlFile(output.filename)
            return (
              <li
                key={output.filename}
                className="flex items-center justify-between bg-white border border-gray-200 rounded-lg px-4 py-3 shadow-sm hover:border-indigo-200 hover:shadow-md transition"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-xl flex-shrink-0" role="img" aria-label={detailedType}>
                    {TYPE_ICONS[detailedType]}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate">
                      {output.filename}
                    </p>
                    <p className="text-xs text-gray-400">
                      {TYPE_LABELS[detailedType]}
                      {extractLangPair(output.filename) && (
                        <span className="ml-1.5 text-gray-300">·</span>
                      )}
                      {extractLangPair(output.filename) && (
                        <span className="ml-1.5">{extractLangPair(output.filename)}</span>
                      )}
                    </p>
                  </div>
                </div>

                {html ? (
                  <a
                    href={output.download_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-4 flex-shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700 border border-indigo-200 hover:border-indigo-400 px-3 py-1.5 rounded-md transition flex items-center gap-1.5"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                    Open
                  </a>
                ) : (
                  <a
                    href={output.download_url}
                    download={output.filename}
                    className="ml-4 flex-shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700 border border-indigo-200 hover:border-indigo-400 px-3 py-1.5 rounded-md transition flex items-center gap-1.5"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    Download
                  </a>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
