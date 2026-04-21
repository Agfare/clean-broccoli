import type { JobOptions } from './types'

// ---------------------------------------------------------------------------
// Input field styling — shared across LoginPage, SettingsPage, LanguagePairInput
// Does NOT include w-full; callers append width utilities as needed.
// ---------------------------------------------------------------------------
export const INPUT_CLASS =
  'border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition'

// ---------------------------------------------------------------------------
// File upload limits — must match the backend enforcement in routes/files.py
// ---------------------------------------------------------------------------
export const MAX_FILE_SIZE_MB = 150
export const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

// ---------------------------------------------------------------------------
// Default job options — exported so they can be imported by tests and stories
// ---------------------------------------------------------------------------
export const DEFAULT_JOB_OPTIONS: JobOptions = {
  remove_duplicates: false,
  move_duplicates_to_separate_file: false,
  remove_untranslated: false,
  move_untranslated_to_separate_file: false,
  remove_tags: false,
  keep_tags_intact: true,
  remove_variables: false,
  keep_variables_intact: true,
  check_numbers: true,
  check_scripts: true,
  check_untranslated: true,
  outputs_tmx: true,
  outputs_clean_xls: true,
  outputs_qa_xls: true,
  outputs_html_report: true,
  merge_to_tmx: false,
}
