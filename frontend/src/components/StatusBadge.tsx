import { JobStatus } from '../types'

interface Props {
  status: JobStatus
}

const config: Record<JobStatus, { label: string; className: string }> = {
  pending: {
    label: 'Pending',
    className: 'bg-gray-100 text-gray-600',
  },
  running: {
    label: 'Running',
    className: 'bg-indigo-100 text-indigo-700',
  },
  complete: {
    label: 'Complete',
    className: 'bg-green-100 text-green-700',
  },
  failed: {
    label: 'Failed',
    className: 'bg-red-100 text-red-700',
  },
  cancelled: {
    label: 'Cancelled',
    className: 'bg-gray-100 text-gray-500',
  },
}

export default function StatusBadge({ status }: Props) {
  const { label, className } = config[status]

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${className}`}
    >
      {status === 'running' && (
        <span className="w-1.5 h-1.5 bg-indigo-600 rounded-full animate-pulse" />
      )}
      {label}
    </span>
  )
}
