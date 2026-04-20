import { useState } from 'react'
import Navbar from '../components/Navbar'
import FileUpload from '../components/FileUpload'
import EngineSelector from '../components/EngineSelector'
import LanguagePairInput from '../components/LanguagePairInput'
import OptionsPanel from '../components/OptionsPanel'
import ProgressBar from '../components/ProgressBar'
import ResultsPanel from '../components/ResultsPanel'
import PreviewModal from '../components/PreviewModal'
import { useJob } from '../hooks/useJob'
import { Engine, JobOptions, UploadedFile } from '../types'

const defaultOptions: JobOptions = {
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
}

export default function HomePage() {
  const [engine, setEngine] = useState<Engine>('none')
  const [sourceLang, setSourceLang] = useState('en')
  const [targetLangs, setTargetLangs] = useState<string[]>(['de'])
  const [isMultilingual, setIsMultilingual] = useState(false)
  const [options, setOptions] = useState<JobOptions>(defaultOptions)
  const [outputPrefix, setOutputPrefix] = useState('')
  const [previewFile, setPreviewFile] = useState<UploadedFile | null>(null)

  const {
    uploadedFiles,
    detectedLanguages,
    currentJob,
    progress,
    progressMessage,
    progressStep,
    results,
    isRunning,
    isUploading,
    uploadProgress,
    isCancelling,
    error,
    uploadFiles,
    removeUploadedFile,
    startJob,
    cancelJob,
    clearJob,
  } = useJob()

  const handleRun = () => {
    if (uploadedFiles.length === 0 || isRunning) return
    startJob({
      file_ids: uploadedFiles.map((f) => f.file_id),
      engine,
      source_lang: sourceLang,
      target_langs: targetLangs,
      options,
      output_prefix: outputPrefix || undefined,
    })
  }

  const canRun = uploadedFiles.length > 0 && !isRunning

  const showProgress = isRunning || (currentJob !== null && !results)
  const showResults = results !== null
  const isCancelled = currentJob?.status === 'cancelled'

  return (
    <>
    <div className="min-h-screen bg-gray-50">
      <Navbar />

      <div className="pt-14">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex flex-col lg:flex-row gap-8">
            {/* Left panel: controls */}
            <div className="lg:w-96 xl:w-[420px] flex-shrink-0 space-y-6">
              {/* File Upload */}
              <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-6">
                <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">
                  Input Files
                </h2>
                <FileUpload
                  onFilesChange={uploadFiles}
                  uploadedFiles={uploadedFiles}
                  onRemoveFile={removeUploadedFile}
                  onPreview={(fileId) =>
                    setPreviewFile(uploadedFiles.find((f) => f.file_id === fileId) ?? null)
                  }
                  isUploading={isUploading}
                  uploadProgress={uploadProgress}
                />
              </div>

              {/* Language pair */}
              <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-6">
                <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">
                  Language Pair
                </h2>
                <LanguagePairInput
                  sourceLang={sourceLang}
                  targetLangs={targetLangs}
                  isMultilingual={isMultilingual}
                  detectedLanguages={detectedLanguages}
                  onSourceChange={setSourceLang}
                  onTargetLangsChange={setTargetLangs}
                  onMultilingualChange={setIsMultilingual}
                />
              </div>

              {/* Output file prefix */}
              <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-6">
                <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">
                  Output File Prefix
                </h2>
                <label className="block text-sm text-gray-600 mb-1">
                  Prefix <span className="text-gray-400">(optional)</span>
                </label>
                <input
                  type="text"
                  value={outputPrefix}
                  onChange={(e) => setOutputPrefix(e.target.value)}
                  placeholder="e.g. project_v2"
                  maxLength={50}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
                />
                <p className="mt-1.5 text-xs text-gray-400">
                  Letters, digits, hyphens and underscores only.
                  {outputPrefix && (
                    <span className="ml-1 text-indigo-500">
                      Files will be named <span className="font-mono">{outputPrefix}_clean_…</span>
                    </span>
                  )}
                </p>
              </div>

              {/* Engine selector */}
              <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-6">
                <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">
                  MT Engine
                </h2>
                <EngineSelector value={engine} onChange={setEngine} />
              </div>

              {/* Run / Cancel buttons */}
              <div className="flex gap-2">
                <button
                  onClick={handleRun}
                  disabled={!canRun}
                  className="flex-1 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 disabled:cursor-not-allowed text-white px-4 py-3 rounded-md font-medium text-sm transition flex items-center justify-center gap-2"
                >
                  {isRunning ? (
                    <>
                      <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Running...
                    </>
                  ) : (
                    <>
                      <svg
                        className="w-4 h-4"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
                        />
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                        />
                      </svg>
                      Run Cleaning Job
                    </>
                  )}
                </button>

                {isRunning && (
                  <button
                    onClick={cancelJob}
                    disabled={isCancelling}
                    title="Cancel this job"
                    className="px-3 py-3 rounded-md font-medium text-sm border border-red-300 text-red-600 hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed transition flex items-center gap-1.5"
                  >
                    {isCancelling ? (
                      <span className="w-4 h-4 border-2 border-red-400 border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    )}
                    {isCancelling ? 'Cancelling…' : 'Cancel'}
                  </button>
                )}
              </div>

              {uploadedFiles.length === 0 && !isRunning && (
                <p className="text-xs text-center text-gray-400">
                  Upload files to enable the run button
                </p>
              )}
            </div>

            {/* Right panel: progress + results */}
            <div className="flex-1 min-w-0">
              {/* Error banner */}
              {error && (
                <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3">
                  <svg
                    className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                  </svg>
                  <div className="flex-1">
                    <p className="text-sm font-medium text-red-700">Job failed</p>
                    <p className="text-sm text-red-600 mt-0.5">{error}</p>
                  </div>
                  <button
                    onClick={clearJob}
                    className="text-red-400 hover:text-red-600 transition"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              )}

              {/* Progress */}
              {showProgress && (
                <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-6 mb-6">
                  <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">
                    Progress
                  </h2>
                  <ProgressBar
                    progress={progress}
                    step={progressStep}
                    message={progressMessage}
                    status={currentJob?.status ?? 'running'}
                  />
                  {isCancelled && (
                    <div className="mt-4 pt-4 border-t border-gray-100">
                      <button
                        onClick={clearJob}
                        className="text-sm text-gray-500 hover:text-gray-700 font-medium transition"
                      >
                        ← Start a new job
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Results */}
              {showResults && (
                <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-6">
                  <ResultsPanel results={results} job={currentJob} />

                  <div className="mt-4 pt-4 border-t border-gray-100">
                    <button
                      onClick={clearJob}
                      className="text-sm text-gray-500 hover:text-gray-700 font-medium transition"
                    >
                      ← Start a new job
                    </button>
                  </div>
                </div>
              )}

              {/* Empty state */}
              {!showProgress && !showResults && !error && (
                <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-12 text-center mb-6">
                  <svg
                    className="w-16 h-16 text-gray-200 mx-auto mb-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1}
                      d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18"
                    />
                  </svg>
                  <h3 className="text-base font-medium text-gray-400 mb-1">
                    Ready to clean
                  </h3>
                  <p className="text-sm text-gray-400">
                    Upload your TM files, configure options, and run a cleaning job.
                    Results will appear here.
                  </p>
                </div>
              )}

              {/* Processing options — always visible, below the action area */}
              <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-6">
                <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">
                  Processing Options
                </h2>
                <OptionsPanel options={options} onChange={setOptions} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    {previewFile && (
      <PreviewModal
        fileId={previewFile.file_id}
        filename={previewFile.filename}
        sourceLang={detectedLanguages[0]}
        targetLang={detectedLanguages[1]}
        onClose={() => setPreviewFile(null)}
      />
    )}
    </>
  )
}
