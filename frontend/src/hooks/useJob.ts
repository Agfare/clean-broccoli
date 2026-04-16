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
  uploadProgress: number   // 0-100; non-zero only while isUploading is true
  isCancelling: boolean
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
  uploadProgress: 0,
  isCancelling: false,
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
    setState((prev) => ({ ...prev, isUploading: true, uploadProgress: 0, error: null }))
    try {
      const res = await jobsApi.upload(files, (pct) => {
        setState((prev) => ({ ...prev, uploadProgress: pct }))
      })
      const newLangs = res.data.flatMap((f) => f.detected_languages ?? [])
      setState((prev) => ({
        ...prev,
        uploadedFiles: [...prev.uploadedFiles, ...res.data],
        detectedLanguages: [...new Set([...prev.detectedLanguages, ...newLangs])],
        isUploading: false,
        uploadProgress: 0,
      }))
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Upload failed'
      setState((prev) => ({
        ...prev,
        isUploading: false,
        uploadProgress: 0,
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
                isCancelling: false,
                results: resultsRes.data,
                currentJob: jobRes.data,
              }))
            } catch {
              setState((prev) => ({
                ...prev,
                isRunning: false,
                isCancelling: false,
                error: 'Failed to fetch results',
              }))
            }
          } else if (parsed.step === 'cancelled') {
            closeEventSource()
            setState((prev) => ({
              ...prev,
              isRunning: false,
              isCancelling: false,
              progressStep: 'cancelled',
              progressMessage: 'Job was cancelled',
              currentJob: prev.currentJob
                ? { ...prev.currentJob, status: 'cancelled' }
                : prev.currentJob,
            }))
          } else if (parsed.step === 'error') {
            closeEventSource()
            setState((prev) => ({
              ...prev,
              isRunning: false,
              isCancelling: false,
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

  const cancelJob = useCallback(async () => {
    const jobId = state.currentJob?.id
    if (!jobId || !state.isRunning || state.isCancelling) return
    setState((prev) => ({ ...prev, isCancelling: true }))
    try {
      await jobsApi.cancel(jobId)
      // SSE stream will receive 'cancelled' step and set isRunning=false
    } catch {
      // If the cancel request fails, just unset the flag — the user can retry
      setState((prev) => ({ ...prev, isCancelling: false }))
    }
  }, [state.currentJob?.id, state.isRunning, state.isCancelling])

  const clearJob = useCallback(() => {
    closeEventSource()
    setState(initialState)
  }, [closeEventSource])

  return {
    ...state,
    uploadFiles,
    removeUploadedFile,
    startJob,
    cancelJob,
    clearJob,
  }
}
