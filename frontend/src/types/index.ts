export interface User {
  id: string
  username: string
  email: string
  is_active: boolean
}

export interface UploadedFile {
  file_id: string
  filename: string
  size: number
  warnings: string[]
}

export type Engine = 'none' | 'anthropic' | 'google' | 'azure' | 'deepl'
export type JobStatus = 'pending' | 'running' | 'complete' | 'failed'

export interface JobOptions {
  remove_duplicates: boolean
  move_duplicates_to_separate_file: boolean
  remove_tags: boolean
  keep_tags_intact: boolean
  remove_variables: boolean
  keep_variables_intact: boolean
  check_numbers: boolean
  check_scripts: boolean
  check_untranslated: boolean
  outputs_tmx: boolean
  outputs_clean_xls: boolean
  outputs_qa_xls: boolean
  outputs_html_report: boolean
}

export interface CreateJobRequest {
  file_ids: string[]
  engine: Engine
  source_lang: string
  target_lang: string
  options: JobOptions
}

export interface Job {
  id: string
  status: JobStatus
  progress: number
  engine: string
  source_lang: string
  target_lang: string
  error_message?: string
  created_at: string
}

export interface ResultFile {
  type: string
  filename: string
  download_url: string
}

export interface JobResults {
  job_id: string
  outputs: ResultFile[]
}

export interface ApiKey {
  id: string
  engine: Engine
  masked_key: string
  created_at: string
}

export interface ProgressEvent {
  step: string
  progress: number
  message: string
}
