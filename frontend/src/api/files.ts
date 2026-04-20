import client from './client'
import { PreviewResponse } from '../types'

interface PreviewOptions {
  limit?: number
  source_lang?: string
  target_lang?: string
}

export const filesApi = {
  preview(fileId: string, opts: PreviewOptions = {}) {
    const params = new URLSearchParams()
    if (opts.limit       != null) params.set('limit',       String(opts.limit))
    if (opts.source_lang)         params.set('source_lang', opts.source_lang)
    if (opts.target_lang)         params.set('target_lang', opts.target_lang)
    const qs = params.toString()
    return client.get<PreviewResponse>(`/files/${fileId}/preview${qs ? `?${qs}` : ''}`)
  },
}
