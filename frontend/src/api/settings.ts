import client from './client'
import { ApiKey, Engine } from '../types'

export const settingsApi = {
  getApiKeys: () => client.get<ApiKey[]>('/settings/api-keys'),

  addApiKey: (data: { engine: Engine; key: string }) =>
    client.post<ApiKey>('/settings/api-keys', data),

  deleteApiKey: (id: string) =>
    client.delete(`/settings/api-keys/${id}`),
}
