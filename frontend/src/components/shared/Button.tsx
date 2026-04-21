import { ButtonHTMLAttributes } from 'react'

/**
 * Styled button with consistent variants.
 *
 * Extends ButtonHTMLAttributes so all native props (type, disabled, onClick,
 * aria-*, etc.) pass through without extra wiring.  Layout utilities (flex-1,
 * w-full, ml-*, etc.) should be passed via `className`.
 */

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'
type Size    = 'sm' | 'md' | 'lg'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
}

const BASE = [
  'inline-flex items-center justify-center gap-2',
  'rounded-md font-medium transition',
  'disabled:cursor-not-allowed',
].join(' ')

const VARIANT: Record<Variant, string> = {
  primary:   'bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-indigo-300',
  secondary: 'border border-gray-300 text-gray-600 hover:text-gray-900 hover:border-gray-400',
  danger:    'border border-red-300 text-red-600 hover:bg-red-50 disabled:opacity-50',
  ghost:     'bg-gray-100 text-gray-600 hover:bg-gray-200',
}

const SIZE: Record<Size, string> = {
  sm: 'px-2.5 py-1   text-xs',
  md: 'px-4   py-2   text-sm',
  lg: 'px-4   py-3   text-sm',
}

export default function Button({
  variant = 'primary',
  size = 'md',
  className = '',
  children,
  ...rest
}: Props) {
  return (
    <button
      className={`${BASE} ${VARIANT[variant]} ${SIZE[size]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
