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
  const { idTokenClaims, isAuthenticated } = useAuth0()

  const client = axios.create({
    baseURL: '/',
    headers: {
      'Content-Type': 'application/json',
    },
  })

  // Attach ID token as bearer — use reactive ref, NOT getIdTokenClaims() (not a function in auth0-vue v2)
  client.interceptors.request.use((config) => {
    if (isAuthenticated.value) {
      const raw = idTokenClaims.value?.__raw
      if (raw) {
        config.headers.Authorization = `Bearer ${raw}`
      } else {
        console.warn('[api] isAuthenticated but idTokenClaims.__raw is empty')
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
