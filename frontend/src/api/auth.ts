import client from './client'
import { User } from '../types'

export const authApi = {
  register: (data: { username: string; email: string; password: string }) =>
    client.post('/auth/register', data),

  login: (data: { email: string; password: string }) =>
    client.post('/auth/login', data),

  logout: () => client.post('/auth/logout'),

  me: () => client.get<User>('/auth/me'),
}
