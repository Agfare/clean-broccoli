/**
 * White rounded card with subtle border and shadow.
 *
 * The pattern `bg-white rounded-lg border border-gray-200 shadow-sm p-6`
 * appeared ~11 times across HomePage, LoginPage, and SettingsPage.
 *
 * Props:
 *  - `noPadding` — omits the default `p-6` (useful when the card contains a
 *    flush table or a custom-padded header section).
 *  - `className` — additional utilities appended after the base classes
 *    (e.g. `mb-6`, `overflow-hidden`, `p-8`, `p-12`).
 */

interface Props {
  children: React.ReactNode
  noPadding?: boolean
  className?: string
}

export default function Card({ children, noPadding = false, className = '' }: Props) {
  return (
    <div
      className={`bg-white rounded-lg border border-gray-200 shadow-sm ${noPadding ? '' : 'p-6'} ${className}`.trim()}
    >
      {children}
    </div>
  )
}
