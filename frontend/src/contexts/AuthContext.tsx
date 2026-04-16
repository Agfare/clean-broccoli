import React, { createContext, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { authApi } from '../api/auth'
import { User } from '../types'

interface AuthContextValue {
  user: User | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  register: (username: string, email: string, password: string) => Promise<void>
}

export const AuthContext = createContext<AuthContextValue>({
  user: null,
  isLoading: true,
  login: async () => {},
  logout: async () => {},
  register: async () => {},
})

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()

  const { data: user = null, isLoading } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      try {
        const res = await authApi.me()
        return res.data
      } catch {
        return null
      }
    },
    staleTime: 5 * 60 * 1000,
    retry: false,
  })

  const loginMutation = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      authApi.login({ email, password }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
    },
  })

  const logoutMutation = useMutation({
    mutationFn: () => authApi.logout(),
    onSuccess: () => {
      queryClient.setQueryData(['auth', 'me'], null)
      queryClient.clear()
    },
  })

  const registerMutation = useMutation({
    mutationFn: ({
      username,
      email,
      password,
    }: {
      username: string
      email: string
      password: string
    }) => authApi.register({ username, email, password }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
    },
  })

  const login = useCallback(
    async (email: string, password: string) => {
      await loginMutation.mutateAsync({ email, password })
      // Await the refetch so `user` is populated before the caller navigates.
      // Without this, ProtectedRoute sees user=null (stale cache) and redirects back to /login.
      await queryClient.refetchQueries({ queryKey: ['auth', 'me'] })
    },
    [loginMutation, queryClient]
  )

  const logout = useCallback(async () => {
    await logoutMutation.mutateAsync()
  }, [logoutMutation])

  const register = useCallback(
    async (username: string, email: string, password: string) => {
      await registerMutation.mutateAsync({ username, email, password })
      await queryClient.refetchQueries({ queryKey: ['auth', 'me'] })
    },
    [registerMutation, queryClient]
  )

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout, register }}>
      {children}
    </AuthContext.Provider>
  )
}
