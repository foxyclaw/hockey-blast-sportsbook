/**
 * Axios client with Auth0 token injection.
 *
 * Usage:
 *   import { useApiClient } from '@/api/client'
 *   const api = useApiClient()
 *   const { data } = await api.get('/api/games')
 */

import axios from 'axios'
import { useAuth0 } from '@auth0/auth0-vue'

export function useApiClient() {
  const { getAccessTokenSilently, isAuthenticated } = useAuth0()

  const client = axios.create({
    baseURL: '/',
    headers: {
      'Content-Type': 'application/json',
    },
  })

  // Attach bearer token when user is authenticated
  client.interceptors.request.use(async (config) => {
    if (isAuthenticated.value) {
      try {
        const token = await getAccessTokenSilently()
        config.headers.Authorization = `Bearer ${token}`
      } catch (e) {
        // Token fetch failed — proceed without auth (public routes)
        console.warn('Could not get access token:', e.message)
      }
    }
    return config
  })

  return client
}

/**
 * Raw unauthenticated client — for public endpoints like GET /api/games
 */
export const publicClient = axios.create({
  baseURL: '/',
  headers: { 'Content-Type': 'application/json' },
})
