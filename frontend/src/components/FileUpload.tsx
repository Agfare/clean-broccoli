import { useRef, useState, DragEvent, ChangeEvent } from 'react'
import { ArrowUpTrayIcon, DocumentTextIcon, EyeIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { XCircleIcon, ExclamationTriangleIcon } from '@heroicons/react/24/solid'
import { UploadedFile } from '../types'
import { MAX_FILE_SIZE_MB, MAX_FILE_SIZE_BYTES } from '../constants'
import { formatBytes } from '../utils/format'
import Spinner from './shared/Spinner'

interface Props {
  onFilesChange: (files: File[]) => void
  uploadedFiles: UploadedFile[]
  onRemoveFile: (fileId: string) => void
  onPreview: (fileId: string) => void
  isUploading: boolean
  uploadProgress?: number  // 0-100; shown when isUploading is true
}

export default function FileUpload({
  onFilesChange,
  uploadedFiles,
  onRemoveFile,
  onPreview,
  isUploading,
  uploadProgress = 0,
}: Props) {
  const [isDragOver, setIsDragOver] = useState(false)
  const [sizeErrors, setSizeErrors] = useState<string[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  function processFiles(raw: File[]) {
    const oversized = raw.filter((f) => f.size > MAX_FILE_SIZE_BYTES)
    const valid = raw.filter((f) => f.size <= MAX_FILE_SIZE_BYTES)
    setSizeErrors(oversized.map((f) => `"${f.name}" exceeds the ${MAX_FILE_SIZE_MB} MB limit`))
    if (valid.length > 0) onFilesChange(valid)
  }

  const handleDragOver = (e: DragEvent) => { e.preventDefault(); setIsDragOver(true) }
  const handleDragLeave = (e: DragEvent) => { e.preventDefault(); setIsDragOver(false) }

  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) processFiles(files)
  }

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    if (files.length > 0) processFiles(files)
    e.target.value = ''  // reset so same file can be re-selected
  }

  return (
    <div>
      {/* Drop zone */}
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`relative border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
          isDragOver
            ? 'border-indigo-500 bg-indigo-50'
            : 'border-gray-300 hover:border-indigo-400 hover:bg-gray-50'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".tmx,.xls,.xlsx,.csv"
          multiple
          className="hidden"
          onChange={handleInputChange}
        />

        {isUploading ? (
          <div className="flex flex-col items-center gap-3 w-full px-2">
            {uploadProgress > 0 ? (
              <>
                <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
                  <div
                    className="bg-indigo-600 h-2 rounded-full transition-all duration-200"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <p className="text-sm text-gray-500">Uploading… {uploadProgress}%</p>
              </>
            ) : (
              <>
                <Spinner size="lg" color="indigo" />
                <p className="text-sm text-gray-500">Uploading…</p>
              </>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <ArrowUpTrayIcon className="w-8 h-8 text-gray-400" strokeWidth={1.5} aria-hidden />
            <p className="text-sm font-medium text-gray-700">Drop TMX, XLS, or CSV files here</p>
            <p className="text-xs text-gray-400">or click to browse files</p>
          </div>
        )}
      </div>

      {/* Oversized-file errors */}
      {sizeErrors.length > 0 && (
        <ul className="mt-2 space-y-1">
          {sizeErrors.map((msg, i) => (
            <li
              key={i}
              className="flex items-start gap-1.5 text-xs text-red-700 bg-red-50 border border-red-200 rounded px-2 py-1.5"
            >
              <XCircleIcon className="w-3.5 h-3.5 flex-shrink-0 mt-0.5 text-red-500" aria-hidden />
              {msg}
            </li>
          ))}
        </ul>
      )}

      {/* Uploaded files list */}
      {uploadedFiles.length > 0 && (
        <ul className="mt-3 space-y-2">
          {uploadedFiles.map((file) => (
            <li
              key={file.file_id}
              className="bg-gray-50 rounded-md border border-gray-200 px-3 py-2"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 min-w-0">
                  <DocumentTextIcon className="w-4 h-4 text-gray-400 flex-shrink-0" aria-hidden />
                  <span className="text-sm text-gray-700 truncate">{file.filename}</span>
                  <span className="text-xs text-gray-400 flex-shrink-0">{formatBytes(file.size)}</span>
                </div>
                <div className="flex items-center gap-1 ml-2 flex-shrink-0">
                  <button
                    onClick={() => onPreview(file.file_id)}
                    className="text-gray-400 hover:text-indigo-500 transition"
                    title="Preview segments"
                    aria-label={`Preview ${file.filename}`}
                  >
                    <EyeIcon className="w-4 h-4" aria-hidden />
                  </button>
                  <button
                    onClick={() => onRemoveFile(file.file_id)}
                    className="text-gray-400 hover:text-red-500 transition"
                    title="Remove file"
                    aria-label={`Remove ${file.filename}`}
                  >
                    <XMarkIcon className="w-4 h-4" aria-hidden />
                  </button>
                </div>
              </div>

              {/* Warnings */}
              {file.warnings.length > 0 && (
                <ul className="mt-1.5 space-y-0.5">
                  {file.warnings.map((w, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-1 text-xs text-yellow-700 bg-yellow-50 border border-yellow-200 rounded px-2 py-1"
                    >
                      <ExclamationTriangleIcon className="w-3.5 h-3.5 flex-shrink-0 mt-0.5 text-yellow-500" aria-hidden />
                      {w}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
