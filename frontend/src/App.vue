<template>
  <div class="min-h-screen bg-base-100 flex flex-col">
    <NavBar />
    <main class="flex-1 container mx-auto px-4 py-6 max-w-3xl">
      <RouterView />
    </main>
    <footer class="footer footer-center p-4 bg-base-300 text-base-content text-xs opacity-60">
      <span>🏒 Hockey Blast Predictions · Not gambling · Just fun</span>
    </footer>
  </div>
</template>

<script setup>
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth0 } from '@auth0/auth0-vue'
import NavBar from '@/components/NavBar.vue'
import { useUserStore } from '@/stores/user'

const { isAuthenticated, isLoading } = useAuth0()
const userStore = useUserStore()
const router = useRouter()

// Load pred user profile when Auth0 confirms authentication
watch(
  () => [isAuthenticated.value, isLoading.value],
  async ([authed, loading]) => {
    if (authed && !loading) {
      await userStore.fetchPredUser()
      // Redirect to identity setup if no hockey profile linked
      if (userStore.needsIdentitySetup) {
        const current = router.currentRoute.value.name
        if (current !== 'identity' && current !== 'callback') {
          router.push({ name: 'identity' })
        }
      }
    } else if (!authed && !loading) {
      userStore.reset()
    }
  },
  { immediate: true }
)
</script>
