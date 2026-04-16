import { Engine } from '../types'

interface Props {
  value: Engine
  onChange: (e: Engine) => void
}

const engines: { value: Engine; label: string; description: string }[] = [
  {
    value: 'none',
    label: 'None',
    description: 'No MT quality check',
  },
  {
    value: 'anthropic',
    label: 'Anthropic (Claude)',
    description: 'Use Claude for quality scoring',
  },
  {
    value: 'google',
    label: 'Google Translate',
    description: 'Use Google Translate for quality scoring',
  },
  {
    value: 'azure',
    label: 'Azure Translator',
    description: 'Use Azure Translator for quality scoring',
  },
  {
    value: 'deepl',
    label: 'DeepL',
    description: 'Use DeepL for quality scoring',
  },
]

export default function EngineSelector({ value, onChange }: Props) {
  return (
    <div>
      <p className="text-xs text-gray-500 mb-3">
        Selected engine will be used to score translation quality
      </p>
      <div className="space-y-2">
        {engines.map((engine) => (
          <label
            key={engine.value}
            className={`flex items-center gap-3 p-3 rounded-md border cursor-pointer transition-colors ${
              value === engine.value
                ? 'border-indigo-400 bg-indigo-50'
                : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
            }`}
          >
            <input
              type="radio"
              name="engine"
              value={engine.value}
              checked={value === engine.value}
              onChange={() => onChange(engine.value)}
              className="text-indigo-600 focus:ring-indigo-500"
            />
            <div>
              <p className="text-sm font-medium text-gray-800">{engine.label}</p>
              <p className="text-xs text-gray-500">{engine.description}</p>
            </div>
          </label>
        ))}
      </div>
    </div>
  )
}
