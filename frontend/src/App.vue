<template>
  <div class="min-h-screen bg-base-100 flex flex-col">
    <NavBar v-if="appReady" />

    <!-- Full-screen loading splash while we figure out who you are -->
    <div v-if="!appReady" class="flex-1 flex items-center justify-center">
      <div class="text-center space-y-4">
        <div class="text-5xl">🏒</div>
        <div class="loading loading-spinner loading-lg text-primary"></div>
        <div class="text-base-content/50 text-sm">Loading...</div>
      </div>
    </div>

    <template v-else>
      <!-- DEBUG PANEL — hidden in prod via v-if="false" -->
      <div v-if="false"></div>
      <main class="flex-1 container mx-auto px-4 py-6 max-w-6xl">
        <RouterView />
      </main>
      <footer class="footer footer-center p-4 bg-base-300 text-base-content text-xs opacity-60">
        <span>🏒 Hockey Blast Sportsbook · Not gambling · Just fun</span>
      </footer>
      <ChatWidget />
    </template>
  </div>
</template>

<script setup>
import { watch, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth0 } from '@auth0/auth0-vue'
import { defineAsyncComponent } from 'vue'
import NavBar from '@/components/NavBar.vue'
import { useUserStore } from '@/stores/user'

const ChatWidget = defineAsyncComponent(() => import('@/components/ChatWidget.vue'))

const { isAuthenticated, isLoading, idTokenClaims, getAccessTokenSilently, checkSession } = useAuth0()
const userStore = useUserStore()
const router = useRouter()

// Attempt silent auth on mount — picks up active session from stats site (same Auth0 tenant)
onMounted(async () => {
  if (!isAuthenticated.value && !isLoading.value) {
    try {
      await checkSession()
    } catch (e) {
      // No active session — user is not logged in
    }
  }
})
const debugToken = ref(null)
const debugLastCall = ref(null)
const debugLastStatus = ref(null)
const debugLastError = ref(null)

// Global axios interceptor to capture last API call for debug panel
import axios from 'axios'
axios.interceptors.request.use(config => {
  debugLastCall.value = `${config.method?.toUpperCase()} ${config.url}`
  debugLastStatus.value = '⏳ pending'
  debugLastError.value = null
  return config
})
axios.interceptors.response.use(
  res => {
    debugLastStatus.value = `✅ ${res.status}`
    return res
  },
  err => {
    debugLastStatus.value = `❌ ${err.response?.status || 'ERR'}`
    debugLastError.value = err.response?.data?.message || err.message
    return Promise.reject(err)
  }
)
const appReady = ref(false)  // blocks rendering until we know user state

// Safety net: if Auth0 takes too long (network issues, domain blocked),
// show the site anyway after 5s — user just won't be logged in
onMounted(() => {
  setTimeout(() => {
    if (!appReady.value) {
      console.warn('[App] Auth0 load timeout — showing site without auth')
      appReady.value = true
    }
  }, 5000)
})

watch(
  () => [isAuthenticated.value, isLoading.value],
  async ([authed, loading]) => {
    if (loading) return  // Auth0 still initializing

    if (authed) {
      try {
        const token = idTokenClaims.value?.__raw
        debugToken.value = token ? token.substring(0, 30) + '…' : 'MISSING'
        await userStore.fetchPredUser(token)
        // Only re-evaluate router guard for onboarding routes (profile-setup etc.)
        const onboardingRoutes = ['profile-setup', 'identity', 'player-prefs']
        if (onboardingRoutes.includes(router.currentRoute.value.name)) {
          await router.replace(router.currentRoute.value.fullPath)
        }
      } catch (e) {
        debugToken.value = 'EXCEPTION: ' + e.message
        console.error('[App] fetchPredUser failed:', e)
      }
    } else {
      userStore.reset()
    }

    appReady.value = true
  },
  { immediate: true }
)
</script>
