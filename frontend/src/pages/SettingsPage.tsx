import { useState, FormEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import Navbar from '../components/Navbar'
import { settingsApi } from '../api/settings'
import { ApiKey, Engine } from '../types'
import { INPUT_CLASS } from '../constants'
import { extractApiError } from '../utils/errors'
import { formatDate } from '../utils/format'

const ENGINE_LABELS: Record<Engine, string> = {
  none: 'None',
  anthropic: 'Anthropic (Claude)',
  google: 'Google Translate',
  azure: 'Azure Translator',
  deepl: 'DeepL',
}

const ENGINE_OPTIONS: Engine[] = ['anthropic', 'google', 'azure', 'deepl']

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [newEngine, setNewEngine] = useState<Engine>('anthropic')
  const [newKey, setNewKey] = useState('')
  const [addError, setAddError] = useState<string | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)

  const {
    data: apiKeys = [],
    isLoading,
    error: fetchError,
  } = useQuery({
    queryKey: ['settings', 'api-keys'],
    queryFn: async () => {
      const res = await settingsApi.getApiKeys()
      return res.data
    },
  })

  const addMutation = useMutation({
    mutationFn: (data: { engine: Engine; key: string }) =>
      settingsApi.addApiKey(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'api-keys'] })
      setNewKey('')
      setAddError(null)
    },
    onError: (err: unknown) => {
      setAddError(extractApiError(err, 'Failed to add key'))
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => settingsApi.deleteApiKey(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'api-keys'] })
      setConfirmDeleteId(null)
    },
  })

  const handleAdd = (e: FormEvent) => {
    e.preventDefault()
    setAddError(null)
    if (!newKey.trim()) {
      setAddError('API key cannot be empty')
      return
    }
    addMutation.mutate({ engine: newEngine, key: newKey.trim() })
  }

  const existingEngines = new Set(apiKeys.map((k) => k.engine))

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />

      <div className="pt-14">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <h1 className="text-xl font-semibold text-gray-900 mb-6">Settings</h1>

          {/* Add new key card */}
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-6 mb-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">
              Add New API Key
            </h2>

            {addError && (
              <div className="mb-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded-md px-3 py-2">
                {addError}
              </div>
            )}

            <form onSubmit={handleAdd} className="flex flex-col sm:flex-row gap-3">
              <select
                value={newEngine}
                onChange={(e) => setNewEngine(e.target.value as Engine)}
                className={`${INPUT_CLASS} sm:w-48 flex-shrink-0`}
              >
                {ENGINE_OPTIONS.map((eng) => (
                  <option key={eng} value={eng}>
                    {ENGINE_LABELS[eng]}
                    {existingEngines.has(eng) ? ' (replace)' : ''}
                  </option>
                ))}
              </select>

              <input
                type="text"
                className={`${INPUT_CLASS} flex-1`}
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                placeholder="Paste your API key here..."
              />

              <button
                type="submit"
                disabled={addMutation.isPending}
                className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white px-4 py-2 rounded-md font-medium text-sm transition flex items-center gap-2 flex-shrink-0"
              >
                {addMutation.isPending && (
                  <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                )}
                Save Key
              </button>
            </form>

            {existingEngines.size > 0 && (
              <p className="mt-2 text-xs text-gray-400">
                Engines marked "(replace)" already have a key — saving will replace it.
              </p>
            )}
          </div>

          {/* Keys table */}
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">
                Saved API Keys
              </h2>
            </div>

            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : fetchError ? (
              <div className="px-6 py-8 text-center">
                <p className="text-sm text-red-600">Failed to load API keys</p>
              </div>
            ) : apiKeys.length === 0 ? (
              <div className="px-6 py-12 text-center">
                <p className="text-sm text-gray-400">No API keys saved yet.</p>
              </div>
            ) : (
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50">
                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                      Engine
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                      Key
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                      Added
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {apiKeys.map((key: ApiKey) => (
                    <tr key={key.id} className="hover:bg-gray-50 transition">
                      <td className="px-6 py-4">
                        <span className="text-sm font-medium text-gray-800">
                          {ENGINE_LABELS[key.engine] ?? key.engine}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <code className="text-sm font-mono text-gray-600 bg-gray-100 px-2 py-0.5 rounded">
                          {key.masked_key}
                        </code>
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-sm text-gray-500">
                          {formatDate(key.created_at)}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right">
                        {confirmDeleteId === key.id ? (
                          <div className="flex items-center justify-end gap-2">
                            <span className="text-xs text-gray-500">Confirm?</span>
                            <button
                              onClick={() => deleteMutation.mutate(key.id)}
                              disabled={deleteMutation.isPending}
                              className="text-xs text-white bg-red-600 hover:bg-red-700 disabled:bg-red-400 px-2.5 py-1 rounded transition"
                            >
                              {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
                            </button>
                            <button
                              onClick={() => setConfirmDeleteId(null)}
                              className="text-xs text-gray-500 hover:text-gray-700 px-2.5 py-1 rounded border border-gray-300 hover:border-gray-400 transition"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setConfirmDeleteId(key.id)}
                            className="text-sm text-red-500 hover:text-red-700 font-medium transition"
                          >
                            Delete
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
