/**
 * Accessible loading spinner. Previously duplicated as inline `<span>`/`<div>`
 * elements with hand-written border classes in App, FileUpload, HomePage,
 * PreviewModal, LoginPage, and SettingsPage.
 */

interface Props {
  /** Diameter: xs=3.5, sm=4, md=5, lg=6, xl=8 (Tailwind units) */
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  /** Border colour — the opposite side is always transparent for the spin effect */
  color?: 'white' | 'indigo' | 'red' | 'gray'
  className?: string
}

const SIZE: Record<NonNullable<Props['size']>, string> = {
  xs: 'w-3.5 h-3.5 border-2',
  sm: 'w-4   h-4   border-2',
  md: 'w-5   h-5   border-2',
  lg: 'w-6   h-6   border-2',
  xl: 'w-8   h-8   border-4',
}

const COLOR: Record<NonNullable<Props['color']>, string> = {
  white:  'border-white  border-t-transparent',
  indigo: 'border-indigo-600 border-t-transparent',
  red:    'border-red-400 border-t-transparent',
  // gray uses a two-tone look — visible border + indigo leading edge
  gray:   'border-gray-300 border-t-indigo-500',
}

export default function Spinner({ size = 'sm', color = 'indigo', className = '' }: Props) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={`inline-block rounded-full animate-spin flex-shrink-0 ${SIZE[size]} ${COLOR[color]} ${className}`}
    />
  )
}
