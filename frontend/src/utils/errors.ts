/**
 * Extract a human-readable error message from an unknown thrown value.
 *
 * Handles the standard Axios error shape (`err.response.data.detail`) that the
 * backend returns for validation and business-logic errors, falling back to
 * `err.message` for plain Error objects, and finally to `fallback`.
 *
 * This replaces four copies of an identical `typeof err === 'object' && 'response' in err…`
 * chain that were previously duplicated across LoginPage, SettingsPage, useJob, and PreviewModal.
 */
export function extractApiError(err: unknown, fallback = 'An error occurred'): string {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const detail = (err as any)?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (err instanceof Error) return err.message
  return fallback
}
