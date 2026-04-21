import { useState } from 'react'
import { PlayCircleIcon, XMarkIcon, TableCellsIcon } from '@heroicons/react/24/outline'
import Navbar from '../components/Navbar'
import FileUpload from '../components/FileUpload'
import EngineSelector from '../components/EngineSelector'
import LanguagePairInput from '../components/LanguagePairInput'
import OptionsPanel from '../components/OptionsPanel'
import ProgressBar from '../components/ProgressBar'
import ResultsPanel from '../components/ResultsPanel'
import PreviewModal from '../components/PreviewModal'
import Alert from '../components/shared/Alert'
import Button from '../components/shared/Button'
import Card from '../components/shared/Card'
import SectionHeader from '../components/shared/SectionHeader'
import Spinner from '../components/shared/Spinner'
import { useJob } from '../hooks/useJob'
import { Engine, UploadedFile } from '../types'
import { DEFAULT_JOB_OPTIONS } from '../constants'

export default function HomePage() {
  const [engine, setEngine] = useState<Engine>('none')
  const [sourceLang, setSourceLang] = useState('en')
  const [targetLangs, setTargetLangs] = useState<string[]>(['de'])
  const [isMultilingual, setIsMultilingual] = useState(false)
  const [options, setOptions] = useState(DEFAULT_JOB_OPTIONS)
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

            {/* ── Left panel: controls ── */}
            <div className="lg:w-80 xl:w-96 flex-shrink-0 space-y-6">

              {/* File Upload */}
              <Card>
                <SectionHeader>Input Files</SectionHeader>
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

                {/* Merge checkbox */}
                <div className="mt-4 pt-4 border-t border-gray-100">
                  <label className="flex items-start gap-2.5 cursor-pointer group">
                    <input
                      type="checkbox"
                      checked={options.merge_to_tmx}
                      onChange={(e) =>
                        setOptions((prev) => ({ ...prev, merge_to_tmx: e.target.checked }))
                      }
                      className="mt-0.5 h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                    />
                    <div>
                      <span className="text-sm font-medium text-gray-700 group-hover:text-gray-900">
                        Merge into single TMX
                      </span>
                      <p className="text-xs text-gray-400 mt-0.5">
                        Combine all input files into one deduplicated multi-language TMX.
                        Applies the same QA checks, tag and variable handling, and
                        duplicate/untranslated filtering.
                      </p>
                    </div>
                  </label>
                </div>
              </Card>

              {/* Language pair */}
              <Card>
                <SectionHeader>Language Pair</SectionHeader>
                <LanguagePairInput
                  sourceLang={sourceLang}
                  targetLangs={targetLangs}
                  isMultilingual={isMultilingual}
                  detectedLanguages={detectedLanguages}
                  onSourceChange={setSourceLang}
                  onTargetLangsChange={setTargetLangs}
                  onMultilingualChange={setIsMultilingual}
                />
              </Card>

              {/* Output file prefix */}
              <Card>
                <SectionHeader>Output File Prefix</SectionHeader>
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
              </Card>

              {/* Run / Cancel buttons */}
              <div className="flex gap-2">
                <Button
                  onClick={handleRun}
                  disabled={!canRun}
                  variant="primary"
                  size="lg"
                  className="flex-1"
                >
                  {isRunning ? (
                    <><Spinner size="sm" color="white" /> Running...</>
                  ) : (
                    <><PlayCircleIcon className="w-4 h-4" aria-hidden /> Run Cleaning Job</>
                  )}
                </Button>

                {isRunning && (
                  <Button
                    onClick={cancelJob}
                    disabled={isCancelling}
                    variant="danger"
                    size="lg"
                    title="Cancel this job"
                  >
                    {isCancelling
                      ? <Spinner size="sm" color="red" />
                      : <XMarkIcon className="w-4 h-4" aria-hidden />}
                    {isCancelling ? 'Cancelling…' : 'Cancel'}
                  </Button>
                )}
              </div>

              {uploadedFiles.length === 0 && !isRunning && (
                <p className="text-xs text-center text-gray-400">
                  Upload files to enable the run button
                </p>
              )}
            </div>

            {/* ── Centre panel: progress + results ── */}
            <div className="flex-1 min-w-0">

              {/* Error banner */}
              {error && (
                <Alert
                  variant="error"
                  title="Job failed"
                  onDismiss={clearJob}
                  className="mb-6"
                >
                  {error}
                </Alert>
              )}

              {/* Progress */}
              {showProgress && (
                <Card className="mb-6">
                  <SectionHeader>Progress</SectionHeader>
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
                </Card>
              )}

              {/* Results */}
              {showResults && (
                <Card className="mb-6">
                  <ResultsPanel results={results} job={currentJob} />
                  <div className="mt-4 pt-4 border-t border-gray-100">
                    <button
                      onClick={clearJob}
                      className="text-sm text-gray-500 hover:text-gray-700 font-medium transition"
                    >
                      ← Start a new job
                    </button>
                  </div>
                </Card>
              )}

              {/* Empty state */}
              {!showProgress && !showResults && !error && (
                <Card className="p-12 text-center mb-6">
                  <TableCellsIcon className="w-16 h-16 text-gray-200 mx-auto mb-4" strokeWidth={1} aria-hidden />
                  <h3 className="text-base font-medium text-gray-400 mb-1">Ready to clean</h3>
                  <p className="text-sm text-gray-400">
                    Upload your TM files, configure options, and run a cleaning job.
                    Results will appear here.
                  </p>
                </Card>
              )}

              {/* Processing options — always visible */}
              <Card>
                <SectionHeader>Processing Options</SectionHeader>
                <OptionsPanel options={options} onChange={setOptions} />
              </Card>
            </div>

            {/* ── Right panel: AI engine ── */}
            <div className="lg:w-64 xl:w-72 flex-shrink-0 space-y-6">
              <Card>
                <SectionHeader>MT Engine</SectionHeader>
                <EngineSelector value={engine} onChange={setEngine} />
              </Card>
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
