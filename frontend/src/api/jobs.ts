import client from './client'
import { UploadedFile, CreateJobRequest, Job, JobResults } from '../types'

export const jobsApi = {
  upload: (files: File[], onProgress?: (pct: number) => void) => {
    const fd = new FormData()
    files.forEach((f) => fd.append('files', f))
    return client.post<UploadedFile[]>('/files/upload', fd, {
      timeout: 300_000, // 5 minutes — allow time for large file uploads
      onUploadProgress: onProgress
        ? (evt) => {
            if (evt.total && evt.total > 0) {
              onProgress(Math.round((evt.loaded / evt.total) * 100))
            }
          }
        : undefined,
    })
  },

  create: (req: CreateJobRequest) => client.post<Job>('/jobs/', req),

  get: (id: string) => client.get<Job>(`/jobs/${id}`),

  cancel: (id: string) => client.post<{ status: string; job_id: string }>(`/jobs/${id}/cancel`),

  results: (id: string) => client.get<JobResults>(`/jobs/${id}/results`),

  downloadUrl: (id: string, filename: string) =>
    `/api/jobs/${id}/download/${filename}`,
}
