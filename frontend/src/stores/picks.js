import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApiClient } from '@/api/client'

export const usePicksStore = defineStore('picks', () => {
  const picks = ref([])
  const loading = ref(false)
  const error = ref(null)
  const total = ref(0)

  async function fetchPicks(params = {}) {
    const api = useApiClient()
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get('/api/picks', { params })
      picks.value = data.picks ?? data
      total.value = data.total ?? picks.value.length
    } catch (e) {
      error.value = e.response?.data?.message ?? e.message
    } finally {
      loading.value = false
    }
  }

  async function submitPick(payload) {
    const api = useApiClient()
    const { data } = await api.post('/api/picks', payload)
    return data
  }

  async function retractPick(pickId) {
    const api = useApiClient()
    await api.delete(`/api/picks/${pickId}`)
    picks.value = picks.value.filter((p) => p.pick_id !== pickId && p.id !== pickId)
  }

  function reset() {
    picks.value = []
    error.value = null
    total.value = 0
  }

  return { picks, loading, error, total, fetchPicks, submitPick, retractPick, reset }
})
