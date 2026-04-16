import client from './client'
import { UploadedFile, CreateJobRequest, Job, JobResults } from '../types'

export const jobsApi = {
  upload: (files: File[]) => {
    const fd = new FormData()
    files.forEach((f) => fd.append('files', f))
    return client.post<UploadedFile[]>('/files/upload', fd)
  },

  create: (req: CreateJobRequest) => client.post<Job>('/jobs/', req),

  get: (id: string) => client.get<Job>(`/jobs/${id}`),

  results: (id: string) => client.get<JobResults>(`/jobs/${id}/results`),

  downloadUrl: (id: string, filename: string) =>
    `/api/jobs/${id}/download/${filename}`,
}
