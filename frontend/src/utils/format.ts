/**
 * Format a byte count as a human-readable string (B / KB / MB).
 * Previously a module-level helper inside FileUpload.tsx.
 */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * Format an ISO 8601 date string as a localised short date (e.g. "Apr 21, 2026").
 * Previously a local helper inside SettingsPage.tsx.
 */
export function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return iso
  }
}
