import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useAuth0 } from '@auth0/auth0-vue'
import { useApiClient } from '@/api/client'

export const useUserStore = defineStore('user', () => {
  const predUser = ref(null)
  const loading = ref(false)
  const error = ref(null)

  const balance = computed(() => predUser.value?.balance ?? 1000)
  const needsIdentitySetup = computed(
    () => predUser.value !== null && predUser.value.hb_human_id === null
  )
  const displayName = computed(() => predUser.value?.display_name ?? '')

  async function fetchPredUser() {
    const api = useApiClient()
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get('/api/auth/me')
      predUser.value = data
    } catch (e) {
      error.value = e.response?.data?.message ?? e.message
    } finally {
      loading.value = false
    }
  }

  function reset() {
    predUser.value = null
    error.value = null
  }

  return { predUser, loading, error, balance, needsIdentitySetup, displayName, fetchPredUser, reset }
})
