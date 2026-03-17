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
      <!-- DEBUG PANEL — remove before prod -->
      <div class="bg-black text-green-400 text-xs font-mono p-3 space-y-1 border-b border-green-700">
        <div>🔐 isAuthenticated: <b>{{ isAuthenticated }}</b> | isLoading: <b>{{ isLoading }}</b></div>
        <div>👤 predUser: <b>{{ userStore.predUser ? userStore.predUser.email : 'null' }}</b> | storeLoading: <b>{{ userStore.loading }}</b></div>
        <div>🪙 token: <b>{{ debugToken || 'null' }}</b></div>
        <div>❌ storeError: <b>{{ userStore.error || 'none' }}</b></div>
        <div>📝 needsNameSetup: <b>{{ userStore.needsNameSetup }}</b> | 🔗 needsIdentitySetup: <b>{{ userStore.needsIdentitySetup }}</b> | 🏒 needsPrefsSetup: <b>{{ userStore.needsPrefsSetup }}</b></div>
      </div>
      <main class="flex-1 container mx-auto px-4 py-6 max-w-3xl">
        <RouterView />
      </main>
      <footer class="footer footer-center p-4 bg-base-300 text-base-content text-xs opacity-60">
        <span>🏒 Hockey Blast Predictions · Not gambling · Just fun</span>
      </footer>
      <ChatWidget v-if="isAuthenticated" />
    </template>
  </div>
</template>

<script setup>
import { watch, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth0 } from '@auth0/auth0-vue'
import { defineAsyncComponent } from 'vue'
import NavBar from '@/components/NavBar.vue'
import { useUserStore } from '@/stores/user'

const ChatWidget = defineAsyncComponent(() => import('@/components/ChatWidget.vue'))

const { isAuthenticated, isLoading, idTokenClaims } = useAuth0()
const userStore = useUserStore()
const router = useRouter()
const debugToken = ref(null)
const appReady = ref(false)  // blocks rendering until we know user state

function redirectIfNeeded() {
  const current = router.currentRoute.value.name
  const onboardingRoutes = ['callback', 'profile-setup', 'identity', 'player-prefs']
  if (userStore.needsNameSetup) {
    if (!onboardingRoutes.includes(current)) router.push({ name: 'profile-setup' })
  } else if (userStore.needsIdentitySetup) {
    if (current !== 'identity' && current !== 'callback') router.push({ name: 'identity' })
  } else if (userStore.needsPrefsSetup) {
    if (!onboardingRoutes.includes(current)) router.push({ name: 'player-prefs' })
  }
}

watch(
  () => [isAuthenticated.value, isLoading.value],
  async ([authed, loading]) => {
    if (loading) return  // Auth0 still initializing, wait

    if (authed) {
      try {
        const token = idTokenClaims.value?.__raw
        debugToken.value = token ? token.substring(0, 30) + '…' : 'MISSING'
        await userStore.fetchPredUser(token)
        redirectIfNeeded()
      } catch (e) {
        debugToken.value = 'EXCEPTION: ' + e.message
        console.error('[App] fetchPredUser failed:', e)
      }
    } else {
      userStore.reset()
    }

    appReady.value = true  // show the app only after we know the state
  },
  { immediate: true }
)
</script>
