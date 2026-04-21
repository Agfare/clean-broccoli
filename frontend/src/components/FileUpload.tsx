import { useRef, useState, DragEvent, ChangeEvent } from 'react'
import { UploadedFile } from '../types'
import { MAX_FILE_SIZE_MB, MAX_FILE_SIZE_BYTES } from '../constants'
import { formatBytes } from '../utils/format'

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

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault()
    setIsDragOver(true)
  }

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
  }

  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) processFiles(files)
  }

  const handleClick = () => {
    inputRef.current?.click()
  }

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    if (files.length > 0) processFiles(files)
    // reset input so same file can be re-selected
    e.target.value = ''
  }

  return (
    <div>
      {/* Drop zone */}
      <div
        onClick={handleClick}
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
                <p className="text-sm text-gray-500">
                  Uploading… {uploadProgress}%
                </p>
              </>
            ) : (
              <>
                <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
                <p className="text-sm text-gray-500">Uploading…</p>
              </>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <svg
              className="w-8 h-8 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
              />
            </svg>
            <p className="text-sm font-medium text-gray-700">
              Drop TMX, XLS, or CSV files here
            </p>
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
              <svg className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
                  clipRule="evenodd"
                />
              </svg>
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
                  <svg
                    className="w-4 h-4 text-gray-400 flex-shrink-0"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                    />
                  </svg>
                  <span className="text-sm text-gray-700 truncate">{file.filename}</span>
                  <span className="text-xs text-gray-400 flex-shrink-0">
                    {formatBytes(file.size)}
                  </span>
                </div>
                <div className="flex items-center gap-1 ml-2 flex-shrink-0">
                  <button
                    onClick={() => onPreview(file.file_id)}
                    className="text-gray-400 hover:text-indigo-500 transition"
                    title="Preview segments"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  </button>
                  <button
                  onClick={() => onRemoveFile(file.file_id)}
                  className="text-gray-400 hover:text-red-500 transition"
                  title="Remove file"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
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
                      <svg
                        className="w-3.5 h-3.5 flex-shrink-0 mt-0.5"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path
                          fillRule="evenodd"
                          d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
                          clipRule="evenodd"
                        />
                      </svg>
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
