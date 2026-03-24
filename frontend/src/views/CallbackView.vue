<template>
  <div class="flex flex-col items-center justify-center min-h-[60vh] gap-4 px-4 text-center">
    <span v-if="!authError" class="loading loading-spinner loading-lg text-primary"></span>
    <p v-if="!authError" class="text-base-content/60 text-sm">Signing you in…</p>

    <template v-if="authError">
      <div class="text-4xl">📧</div>
      <h2 class="text-xl font-bold">Check your email</h2>
      <p class="text-base-content/70 max-w-sm">
        We sent a verification link to your email address.<br>
        Click it to activate your account, then try signing in again.
      </p>
      <p class="text-xs text-base-content/40">Didn't get it? Check your spam folder.</p>
      <div class="flex flex-col gap-2 mt-2 w-full max-w-xs">
        <button @click="loginWithGoogle" class="btn btn-primary">Sign in with Google instead</button>
        <button @click="loginWithEmail" class="btn btn-ghost btn-sm">← Back to home</button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth0 } from '@auth0/auth0-vue'
import { useUserStore } from '@/stores/user'

const { isAuthenticated, isLoading, error, idTokenClaims, loginWithRedirect } = useAuth0()
const userStore = useUserStore()
const router = useRouter()
const authError = ref(null)
const authErrorDetail = ref(null)

const loginWithGoogle = () => loginWithRedirect({ authorizationParams: { connection: 'google-oauth2' } })
const loginWithEmail = () => { window.location.href = '/' }

// Check URL params immediately — access.deny() comes back as ?error=access_denied
onMounted(() => {
  const params = new URLSearchParams(window.location.search)
  const urlError = params.get('error')
  const urlDesc = params.get('error_description')
  if (urlError) {
    authError.value = urlDesc || urlError
    authErrorDetail.value = urlError
  }
})

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
      if (!error.value && !authError.value) router.replace({ name: 'home' })
      return
    }
    await userStore.fetchPredUser(idTokenClaims.value?.__raw)
    // Restore the page they were trying to visit before login
    const { appState } = useAuth0()
    const returnTo = appState?.value?.returnTo
    router.replace(returnTo && returnTo !== '/' ? returnTo : { name: 'home' })
  },
  { immediate: true }
)
</script>
