import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

export const useUserStore = defineStore('user', () => {
  const predUser = ref(null)
  const loading = ref(false)
  const error = ref(null)
  let _cachedToken = null

  const balance = computed(() => predUser.value?.balance ?? 0)
  const displayName = computed(() => predUser.value?.display_name ?? '')

  // Name is "missing" if it contains no space (e.g. just an email or single word)
  const needsNameSetup = computed(() => {
    if (!predUser.value) return false
    const name = predUser.value.display_name || ''
    return !name.includes(' ')
  })

  const needsIdentitySetup = computed(
    () => predUser.value !== null && !needsNameSetup.value && predUser.value.hb_human_id === null
  )

  const needsPrefsSetup = computed(
    () => predUser.value !== null && !needsNameSetup.value && !predUser.value.preferences_completed
  )

  async function fetchPredUser(idToken = null) {
    if (idToken) _cachedToken = idToken
    loading.value = true
    error.value = null
    try {
      const headers = _cachedToken ? { Authorization: `Bearer ${_cachedToken}` } : {}
      const { data } = await axios.get('/auth/me', { headers })
      predUser.value = data
    } catch (e) {
      const msg = e.response?.data?.message ?? e.message
      error.value = `[${e.response?.status ?? 'ERR'}] ${msg}`
      console.error('[fetchPredUser]', e.response?.status, e.response?.data, e.message)
    } finally {
      loading.value = false
    }
  }

  function reset() {
    predUser.value = null
    error.value = null
    _cachedToken = null
  }

  return { predUser, loading, error, balance, needsIdentitySetup, needsNameSetup, needsPrefsSetup, displayName, fetchPredUser, reset }
})
