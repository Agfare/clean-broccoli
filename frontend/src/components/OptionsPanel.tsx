import { JobOptions } from '../types'

interface Props {
  options: JobOptions
  onChange: (opts: JobOptions) => void
}

interface CheckboxProps {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
}

function Checkbox({ label, checked, onChange }: CheckboxProps) {
  return (
    <label className="flex items-center gap-2.5 cursor-pointer group">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 focus:ring-2 cursor-pointer"
      />
      <span className="text-sm text-gray-700 group-hover:text-gray-900 transition">
        {label}
      </span>
    </label>
  )
}

function SectionHeader({ title }: { title: string }) {
  return (
    <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
      {title}
    </h3>
  )
}

export default function OptionsPanel({ options, onChange }: Props) {
  const set = <K extends keyof JobOptions>(key: K, value: JobOptions[K]) => {
    onChange({ ...options, [key]: value })
  }

  return (
    <div className="space-y-6">
      {/* Duplicate handling */}
      <div>
        <SectionHeader title="Duplicate handling" />
        <div className="space-y-2">
          <Checkbox
            label="Remove duplicates from clean output"
            checked={options.remove_duplicates}
            onChange={(v) => set('remove_duplicates', v)}
          />
          <Checkbox
            label="Move duplicates to separate file"
            checked={options.move_duplicates_to_separate_file}
            onChange={(v) => set('move_duplicates_to_separate_file', v)}
          />
        </div>
        {options.remove_duplicates && options.move_duplicates_to_separate_file && (
          <p className="mt-2 text-xs text-indigo-600">
            Duplicates will be saved to a separate file first, then removed from the clean output.
          </p>
        )}
      </div>

      {/* Tag & Variable handling */}
      <div>
        <SectionHeader title="Tag & Variable handling" />
        <div className="space-y-2">
          <Checkbox
            label="Remove tags (strip inline tags)"
            checked={options.remove_tags}
            onChange={(v) => set('remove_tags', v)}
          />
          <Checkbox
            label="Keep tags intact (preserve, just check)"
            checked={options.keep_tags_intact}
            onChange={(v) => set('keep_tags_intact', v)}
          />
          <Checkbox
            label="Remove variables"
            checked={options.remove_variables}
            onChange={(v) => set('remove_variables', v)}
          />
          <Checkbox
            label="Keep variables intact"
            checked={options.keep_variables_intact}
            onChange={(v) => set('keep_variables_intact', v)}
          />
        </div>
      </div>

      {/* QA Checks */}
      <div>
        <SectionHeader title="QA Checks" />
        <div className="space-y-2">
          <Checkbox
            label="Check numbers"
            checked={options.check_numbers}
            onChange={(v) => set('check_numbers', v)}
          />
          <Checkbox
            label="Check character scripts"
            checked={options.check_scripts}
            onChange={(v) => set('check_scripts', v)}
          />
          <Checkbox
            label="Check untranslated segments"
            checked={options.check_untranslated}
            onChange={(v) => set('check_untranslated', v)}
          />
        </div>
      </div>

      {/* Output formats */}
      <div>
        <SectionHeader title="Output formats" />
        <div className="space-y-2">
          <Checkbox
            label="TMX file"
            checked={options.outputs_tmx}
            onChange={(v) => set('outputs_tmx', v)}
          />
          <Checkbox
            label="Clean XLS"
            checked={options.outputs_clean_xls}
            onChange={(v) => set('outputs_clean_xls', v)}
          />
          <Checkbox
            label="QA XLS (with issue column)"
            checked={options.outputs_qa_xls}
            onChange={(v) => set('outputs_qa_xls', v)}
          />
          <Checkbox
            label="HTML Report"
            checked={options.outputs_html_report}
            onChange={(v) => set('outputs_html_report', v)}
          />
        </div>
      </div>
    </div>
  )
}
