import { ExclamationCircleIcon, XMarkIcon } from '@heroicons/react/24/outline'

/**
 * Alert banner for error and warning messages.
 *
 * Two visual modes are chosen automatically:
 *  - **Simple** (no `title`, no `onDismiss`): compact coloured box — used for
 *    inline form errors in LoginPage and SettingsPage.
 *  - **Full** (has `title` or `onDismiss`): padded card with leading icon,
 *    title, body text, and optional dismiss button — used for the job-failed
 *    banner in HomePage.
 */

type Variant = 'error' | 'warning'

interface AlertStyles {
  bg: string
  border: string
  icon: string
  title: string
  body: string
  dismiss: string
}

const STYLES: Record<Variant, AlertStyles> = {
  error: {
    bg:      'bg-red-50',
    border:  'border-red-200',
    icon:    'text-red-500',
    title:   'text-red-700',
    body:    'text-red-600',
    dismiss: 'text-red-400 hover:text-red-600',
  },
  warning: {
    bg:      'bg-yellow-50',
    border:  'border-yellow-200',
    icon:    'text-yellow-500',
    title:   'text-yellow-700',
    body:    'text-yellow-600',
    dismiss: 'text-yellow-400 hover:text-yellow-600',
  },
}

interface Props {
  variant: Variant
  /** Optional bold heading shown above the body text */
  title?: string
  /** If provided, a dismiss ✕ button is rendered and calls this on click */
  onDismiss?: () => void
  className?: string
  children: React.ReactNode
}

export default function Alert({ variant, title, onDismiss, className = '', children }: Props) {
  const s = STYLES[variant]

  // Simple mode — no icon, no title, no dismiss button
  if (!title && !onDismiss) {
    return (
      <div
        className={`${s.bg} border ${s.border} ${s.body} text-sm rounded-md px-3 py-2 ${className}`}
        role="alert"
      >
        {children}
      </div>
    )
  }

  // Full mode — icon + optional title + body + optional dismiss
  return (
    <div
      className={`${s.bg} border ${s.border} rounded-lg p-4 flex items-start gap-3 ${className}`}
      role="alert"
    >
      <ExclamationCircleIcon className={`w-5 h-5 ${s.icon} flex-shrink-0 mt-0.5`} aria-hidden />
      <div className="flex-1">
        {title && <p className={`text-sm font-medium ${s.title}`}>{title}</p>}
        <p className={`text-sm ${s.body}${title ? ' mt-0.5' : ''}`}>{children}</p>
      </div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          aria-label="Dismiss"
          className={`${s.dismiss} transition flex-shrink-0`}
        >
          <XMarkIcon className="w-4 h-4" aria-hidden />
        </button>
      )}
    </div>
  )
}
