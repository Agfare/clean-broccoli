import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  withCredentials: true,
})

client.interceptors.response.use(
  (response) => response,
  (error) => {
    // Do NOT force a redirect here — React Router + ProtectedRoute handle navigation
    // declaratively. A forced window.location reload fights with TanStack Query's
    // cache, causing the login redirect loop (user=null in stale cache → redirect).
    return Promise.reject(error)
  }
)

export default client
