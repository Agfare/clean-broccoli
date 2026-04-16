import { JobStatus } from '../types'

interface Props {
  progress: number
  step: string
  message: string
  status: JobStatus
}

export default function ProgressBar({ progress, step, message, status }: Props) {
  const clampedProgress = Math.min(100, Math.max(0, progress))

  const barColor =
    status === 'failed'
      ? 'bg-red-500'
      : status === 'complete'
      ? 'bg-green-500'
      : 'bg-indigo-600'

  const trackColor =
    status === 'failed'
      ? 'bg-red-100'
      : status === 'complete'
      ? 'bg-green-100'
      : 'bg-indigo-100'

  return (
    <div className="space-y-2">
      {/* Step label and percentage */}
      <div className="flex items-center justify-between">
        {step && (
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            {step}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {status === 'complete' && (
            <svg
              className="w-4 h-4 text-green-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2.5}
                d="M5 13l4 4L19 7"
              />
            </svg>
          )}
          {status === 'failed' && (
            <svg
              className="w-4 h-4 text-red-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2.5}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          )}
          <span
            className={`text-sm font-medium ${
              status === 'failed'
                ? 'text-red-600'
                : status === 'complete'
                ? 'text-green-600'
                : 'text-indigo-700'
            }`}
          >
            {clampedProgress}%
          </span>
        </div>
      </div>

      {/* Bar track */}
      <div className={`w-full h-2.5 rounded-full ${trackColor}`}>
        <div
          className={`h-2.5 rounded-full transition-all duration-300 ${barColor} ${
            status === 'running' ? 'animate-pulse' : ''
          }`}
          style={{ width: `${clampedProgress}%` }}
        />
      </div>

      {/* Message */}
      {message && (
        <p
          className={`text-sm ${
            status === 'failed'
              ? 'text-red-600'
              : status === 'complete'
              ? 'text-green-700'
              : 'text-gray-600'
          }`}
        >
          {message}
        </p>
      )}
    </div>
  )
}
