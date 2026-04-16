import { JobResults, Job } from '../types'

interface Props {
  results: JobResults | null
  job: Job | null
}

function getFileIcon(type: string): string {
  switch (type.toLowerCase()) {
    case 'tmx':
      return '📄'
    case 'clean_xls':
    case 'xls':
    case 'xlsx':
      return '📊'
    case 'qa_xls':
      return '📋'
    case 'html_report':
    case 'html':
      return '📈'
    default:
      return '📁'
  }
}

function isHtmlReport(type: string, filename: string): boolean {
  return (
    type.toLowerCase().includes('html') ||
    filename.toLowerCase().endsWith('.html') ||
    filename.toLowerCase().endsWith('.htm')
  )
}

export default function ResultsPanel({ results, job }: Props) {
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

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-semibold text-gray-800">Results</h2>
        {job && (
          <div className="text-xs text-gray-500">
            Job{' '}
            <span className="font-mono text-gray-700">{job.id.slice(0, 8)}…</span>
            {' · '}
            {job.source_lang} → {job.target_lang}
          </div>
        )}
      </div>

      <ul className="space-y-2">
        {results.outputs.map((output) => {
          const html = isHtmlReport(output.type, output.filename)
          return (
            <li
              key={output.filename}
              className="flex items-center justify-between bg-white border border-gray-200 rounded-lg px-4 py-3 shadow-sm hover:border-indigo-200 hover:shadow-md transition"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="text-xl flex-shrink-0" role="img" aria-label={output.type}>
                  {getFileIcon(output.type)}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">
                    {output.filename}
                  </p>
                  <p className="text-xs text-gray-400 capitalize">
                    {output.type.replace(/_/g, ' ')}
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
    </div>
  )
}
