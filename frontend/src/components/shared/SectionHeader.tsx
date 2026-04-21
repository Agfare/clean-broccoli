/**
 * Card-level section heading.
 *
 * The class string `text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4`
 * was repeated on `<h2>` elements in every Card across HomePage and SettingsPage.
 *
 * Usage:
 *   <SectionHeader>Input Files</SectionHeader>
 *   <SectionHeader className="mb-0">Saved API Keys</SectionHeader>
 */

interface Props {
  children: React.ReactNode
  /** Extra utilities appended after base classes (e.g. `mb-0` to remove spacing) */
  className?: string
}

export default function SectionHeader({ children, className = '' }: Props) {
  return (
    <h2
      className={`text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4 ${className}`.trim()}
    >
      {children}
    </h2>
  )
}
