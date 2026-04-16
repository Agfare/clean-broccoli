interface Props {
  sourceLang: string
  targetLang: string
  onSourceChange: (val: string) => void
  onTargetChange: (val: string) => void
}

const inputClass =
  'w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition'

export default function LanguagePairInput({
  sourceLang,
  targetLang,
  onSourceChange,
  onTargetChange,
}: Props) {
  return (
    <div>
      <div className="flex gap-3">
        <div className="flex-1">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Source language
          </label>
          <input
            type="text"
            className={inputClass}
            value={sourceLang}
            onChange={(e) => onSourceChange(e.target.value)}
            placeholder="en"
            maxLength={10}
          />
        </div>

        <div className="flex items-end pb-2 text-gray-400">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
          </svg>
        </div>

        <div className="flex-1">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Target language
          </label>
          <input
            type="text"
            className={inputClass}
            value={targetLang}
            onChange={(e) => onTargetChange(e.target.value)}
            placeholder="de"
            maxLength={10}
          />
        </div>
      </div>
      <p className="mt-1.5 text-xs text-gray-400">
        Use ISO 639-1 codes (e.g. en, de, fr, zh)
      </p>
    </div>
  )
}
