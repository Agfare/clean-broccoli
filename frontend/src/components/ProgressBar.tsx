import { CheckIcon, XMarkIcon } from '@heroicons/react/24/outline'
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
    status === 'failed'    ? 'bg-red-500'   :
    status === 'complete'  ? 'bg-green-500' :
    status === 'cancelled' ? 'bg-gray-400'  :
                             'bg-indigo-600'

  const trackColor =
    status === 'failed'    ? 'bg-red-100'   :
    status === 'complete'  ? 'bg-green-100' :
    status === 'cancelled' ? 'bg-gray-100'  :
                             'bg-indigo-100'

  const textColor =
    status === 'failed'    ? 'text-red-600'   :
    status === 'complete'  ? 'text-green-600' :
    status === 'cancelled' ? 'text-gray-500'  :
                             'text-indigo-700'

  const messageColor =
    status === 'failed'    ? 'text-red-600'   :
    status === 'complete'  ? 'text-green-700' :
    status === 'cancelled' ? 'text-gray-500'  :
                             'text-gray-600'

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
            <CheckIcon className="w-4 h-4 text-green-600" strokeWidth={2.5} aria-hidden />
          )}
          {(status === 'failed' || status === 'cancelled') && (
            <XMarkIcon
              className={`w-4 h-4 ${status === 'cancelled' ? 'text-gray-400' : 'text-red-600'}`}
              strokeWidth={2.5}
              aria-hidden
            />
          )}
          <span className={`text-sm font-medium ${textColor}`}>
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
      {message && <p className={`text-sm ${messageColor}`}>{message}</p>}
    </div>
  )
}
