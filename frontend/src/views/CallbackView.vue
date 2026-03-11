<template>
  <div class="flex flex-col items-center justify-center min-h-[60vh] gap-4">
    <span class="loading loading-spinner loading-lg text-primary"></span>
    <p class="text-base-content/60 text-sm">Signing you in…</p>
  </div>
</template>

<script setup>
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth0 } from '@auth0/auth0-vue'
import { useUserStore } from '@/stores/user'

const { isAuthenticated, isLoading } = useAuth0()
const userStore = useUserStore()
const router = useRouter()

watch(
  () => [isAuthenticated.value, isLoading.value],
  async ([authed, loading]) => {
    if (loading) return
    if (!authed) {
      // Auth failed or cancelled — go home
      router.replace({ name: 'home' })
      return
    }
    // Fetch the pred user profile
    await userStore.fetchPredUser()
    if (userStore.needsIdentitySetup) {
      router.replace({ name: 'identity' })
    } else {
      router.replace({ name: 'home' })
    }
  },
  { immediate: true }
)
</script>
