<template>
  <div class="flex flex-col items-center justify-center min-h-[60vh] gap-4">
    <span v-if="!authError" class="loading loading-spinner loading-lg text-primary"></span>
    <p class="text-base-content/60 text-sm">{{ authError ? 'Login failed' : 'Signing you in…' }}</p>
    <div v-if="authError" class="alert alert-error max-w-lg text-xs font-mono">{{ authError }}</div>
    <div v-if="authError" class="text-xs text-base-content/50">{{ authErrorDetail }}</div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth0 } from '@auth0/auth0-vue'
import { useUserStore } from '@/stores/user'

const { isAuthenticated, isLoading, error, idTokenClaims } = useAuth0()
const userStore = useUserStore()
const router = useRouter()
const authError = ref(null)
const authErrorDetail = ref(null)

watch(error, (err) => {
  if (err) {
    authError.value = err.message || String(err)
    authErrorDetail.value = err.error_description || err.error || ''
  }
})

watch(
  () => [isAuthenticated.value, isLoading.value],
  async ([authed, loading]) => {
    if (loading) return
    if (!authed) {
      if (!error.value) router.replace({ name: 'home' })
      return
    }
    await userStore.fetchPredUser(idTokenClaims.value?.__raw)
    // Identity linking is optional — always go home after login
    router.replace({ name: 'home' })
  },
  { immediate: true }
)
</script>
