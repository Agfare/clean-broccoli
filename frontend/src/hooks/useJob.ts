import { useState, useRef, useCallback } from 'react'
import { jobsApi } from '../api/jobs'
import {
  UploadedFile,
  Job,
  JobResults,
  CreateJobRequest,
  ProgressEvent,
} from '../types'

interface JobState {
  uploadedFiles: UploadedFile[]
  detectedLanguages: string[]
  currentJob: Job | null
  progress: number
  progressMessage: string
  progressStep: string
  results: JobResults | null
  isRunning: boolean
  isUploading: boolean
  error: string | null
}

const initialState: JobState = {
  uploadedFiles: [],
  detectedLanguages: [],
  currentJob: null,
  progress: 0,
  progressMessage: '',
  progressStep: '',
  results: null,
  isRunning: false,
  isUploading: false,
  error: null,
}

export function useJob() {
  const [state, setState] = useState<JobState>(initialState)
  const eventSourceRef = useRef<EventSource | null>(null)

  const closeEventSource = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }, [])

  const uploadFiles = useCallback(async (files: File[]) => {
    setState((prev) => ({ ...prev, isUploading: true, error: null }))
    try {
      const res = await jobsApi.upload(files)
      const newLangs = res.data.flatMap((f) => f.detected_languages ?? [])
      setState((prev) => ({
        ...prev,
        uploadedFiles: [...prev.uploadedFiles, ...res.data],
        detectedLanguages: [...new Set([...prev.detectedLanguages, ...newLangs])],
        isUploading: false,
      }))
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Upload failed'
      setState((prev) => ({
        ...prev,
        isUploading: false,
        error: message,
      }))
    }
  }, [])

  const removeUploadedFile = useCallback((fileId: string) => {
    setState((prev) => {
      const remaining = prev.uploadedFiles.filter((f) => f.file_id !== fileId)
      const langs = [...new Set(remaining.flatMap((f) => f.detected_languages ?? []))]
      return { ...prev, uploadedFiles: remaining, detectedLanguages: langs }
    })
  }, [])

  const startJob = useCallback(
    async (req: CreateJobRequest) => {
      closeEventSource()
      setState((prev) => ({
        ...prev,
        isRunning: true,
        error: null,
        progress: 0,
        progressMessage: 'Starting job...',
        progressStep: 'pending',
        results: null,
        currentJob: null,
      }))

      let jobId: string
      try {
        const res = await jobsApi.create(req)
        jobId = res.data.id
        setState((prev) => ({ ...prev, currentJob: res.data }))
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : 'Failed to create job'
        setState((prev) => ({
          ...prev,
          isRunning: false,
          error: message,
        }))
        return
      }

      const es = new EventSource(`/api/jobs/${jobId}/stream`, {
        withCredentials: true,
      })
      eventSourceRef.current = es

      es.onmessage = async (event: MessageEvent) => {
        try {
          const parsed: ProgressEvent = JSON.parse(event.data as string)
          setState((prev) => ({
            ...prev,
            progress: parsed.progress,
            progressMessage: parsed.message,
            progressStep: parsed.step,
          }))

          if (parsed.step === 'complete') {
            closeEventSource()
            try {
              const resultsRes = await jobsApi.results(jobId)
              const jobRes = await jobsApi.get(jobId)
              setState((prev) => ({
                ...prev,
                isRunning: false,
                results: resultsRes.data,
                currentJob: jobRes.data,
              }))
            } catch {
              setState((prev) => ({
                ...prev,
                isRunning: false,
                error: 'Failed to fetch results',
              }))
            }
          } else if (parsed.step === 'error') {
            closeEventSource()
            setState((prev) => ({
              ...prev,
              isRunning: false,
              error: parsed.message,
            }))
          }
        } catch {
          // ignore parse errors
        }
      }

      es.onerror = () => {
        closeEventSource()
        setState((prev) => ({
          ...prev,
          isRunning: false,
          error: 'Connection to server lost. The job may still be running.',
        }))
      }
    },
    [closeEventSource]
  )

  const clearJob = useCallback(() => {
    closeEventSource()
    setState(initialState)
  }, [closeEventSource])

  return {
    ...state,
    uploadFiles,
    removeUploadedFile,
    startJob,
    clearJob,
  }
}
