import { useState, KeyboardEvent } from 'react'
import { INPUT_CLASS } from '../constants'

interface Props {
  sourceLang: string
  targetLangs: string[]
  isMultilingual: boolean
  detectedLanguages: string[]
  onSourceChange: (val: string) => void
  onTargetLangsChange: (langs: string[]) => void
  onMultilingualChange: (val: boolean) => void
}

export default function LanguagePairInput({
  sourceLang,
  targetLangs,
  isMultilingual,
  detectedLanguages,
  onSourceChange,
  onTargetLangsChange,
  onMultilingualChange,
}: Props) {
  const [addInput, setAddInput] = useState('')

  const handleMultilingualToggle = (checked: boolean) => {
    if (!checked) {
      // switching to single: keep first lang only
      onTargetLangsChange(targetLangs.length > 0 ? [targetLangs[0]] : [''])
    }
    onMultilingualChange(checked)
  }

  const removeTargetLang = (lang: string) => {
    onTargetLangsChange(targetLangs.filter((l) => l !== lang))
  }

  const addTargetLang = (raw: string) => {
    const lang = raw.trim().toLowerCase().replace(/[^a-z-]/g, '')
    if (lang && !targetLangs.includes(lang)) {
      onTargetLangsChange([...targetLangs, lang])
    }
    setAddInput('')
  }

  const handleAddKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      addTargetLang(addInput)
    } else if (e.key === 'Backspace' && addInput === '' && targetLangs.length > 0) {
      onTargetLangsChange(targetLangs.slice(0, -1))
    }
  }

  const unaddedDetected = detectedLanguages.filter((l) => !targetLangs.includes(l))

  return (
    <div className="space-y-3">
      {/* Multilingual toggle */}
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={isMultilingual}
          onChange={(e) => handleMultilingualToggle(e.target.checked)}
          className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
        />
        <span className="text-sm text-gray-700">Multilingual file</span>
      </label>

      {/* Source language */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Source language
        </label>
        <input
          type="text"
          className={`${INPUT_CLASS} w-full`}
          value={sourceLang}
          onChange={(e) => onSourceChange(e.target.value)}
          placeholder="en"
          maxLength={10}
        />
      </div>

      {/* Target language(s) */}
      {!isMultilingual ? (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Target language
          </label>
          <input
            type="text"
            className={`${INPUT_CLASS} w-full`}
            value={targetLangs[0] ?? ''}
            onChange={(e) => onTargetLangsChange([e.target.value])}
            placeholder="de"
            maxLength={10}
          />
        </div>
      ) : (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Target languages
          </label>

          {/* Tag input box */}
          <div className="min-h-[42px] w-full border border-gray-300 rounded-md px-2 py-1.5 flex flex-wrap gap-1.5 focus-within:ring-2 focus-within:ring-indigo-500 focus-within:border-transparent transition bg-white">
            {targetLangs.map((lang) => (
              <span
                key={lang}
                className="inline-flex items-center gap-1 bg-indigo-100 text-indigo-800 text-xs font-medium px-2 py-0.5 rounded-full"
              >
                {lang}
                <button
                  type="button"
                  onClick={() => removeTargetLang(lang)}
                  className="text-indigo-500 hover:text-indigo-700 leading-none"
                  aria-label={`Remove ${lang}`}
                >
                  ×
                </button>
              </span>
            ))}
            <input
              type="text"
              value={addInput}
              onChange={(e) => setAddInput(e.target.value)}
              onKeyDown={handleAddKeyDown}
              placeholder={targetLangs.length === 0 ? 'add lang…' : ''}
              maxLength={5}
              className="text-sm outline-none flex-1 min-w-[60px] bg-transparent py-0.5"
            />
          </div>

          {/* Detected language suggestions */}
          {unaddedDetected.length > 0 && (
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-gray-400">Detected:</span>
              {unaddedDetected.map((lang) => (
                <button
                  key={lang}
                  type="button"
                  onClick={() => onTargetLangsChange([...targetLangs, lang])}
                  className="text-xs bg-gray-100 hover:bg-indigo-100 hover:text-indigo-700 text-gray-600 px-2 py-0.5 rounded-full border border-gray-200 hover:border-indigo-300 transition"
                >
                  + {lang}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <p className="text-xs text-gray-400">
        {isMultilingual
          ? 'Type a code and press Enter or comma to add. Press Backspace to remove.'
          : 'Use ISO 639-1 codes (e.g. en, de, fr, zh)'}
      </p>
    </div>
  )
}
