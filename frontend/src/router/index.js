import { createRouter, createWebHistory } from 'vue-router'
import { authGuard } from '@auth0/auth0-vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/HomeView.vue'),
    },
    {
      path: '/picks',
      name: 'picks',
      component: () => import('@/views/PicksView.vue'),
      beforeEnter: authGuard,
    },
    {
      path: '/leagues',
      name: 'leagues',
      component: () => import('@/views/LeaguesView.vue'),
      beforeEnter: authGuard,
    },
    {
      path: '/leagues/:id',
      name: 'standings',
      component: () => import('@/views/StandingsView.vue'),
      beforeEnter: authGuard,
    },
    {
      path: '/profile-setup',
      name: 'profile-setup',
      component: () => import('@/views/ProfileSetupView.vue'),
      beforeEnter: authGuard,
    },
    {
      path: '/identity',
      name: 'identity',
      component: () => import('@/views/IdentityView.vue'),
      beforeEnter: authGuard,
    },
    {
      path: '/player-prefs',
      name: 'player-prefs',
      component: () => import('@/views/PlayerPrefsView.vue'),
      beforeEnter: authGuard,
    },
    {
      path: '/fantasy',
      name: 'fantasy',
      component: () => import('@/views/FantasyView.vue'),
    },
    {
      path: '/my-fantasy',
      name: 'my-fantasy',
      component: () => import('@/views/MyFantasyView.vue'),
    },
    {
      path: '/fantasy/:id',
      name: 'fantasy-league',
      component: () => import('@/views/FantasyLeagueView.vue'),
      // Public — auth only required for join/pick actions within the view
    },
    {
      path: '/free-agents',
      name: 'free-agents',
      component: () => import('@/views/FreeAgentsView.vue'),
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('@/views/AdminView.vue'),
      beforeEnter: authGuard,
      meta: { requiresAdmin: true },
    },
    {
      path: '/admin/predictions',
      name: 'admin-predictions',
      component: () => import('@/views/PredictionAnalysisView.vue'),
      beforeEnter: authGuard,
      meta: { requiresAdmin: true },
    },
    {
      path: '/callback',
      name: 'callback',
      component: () => import('@/views/CallbackView.vue'),
    },
    {
      path: '/privacy',
      name: 'privacy',
      component: () => import('@/views/PrivacyView.vue'),
    },
    {
      path: '/terms',
      name: 'terms',
      component: () => import('@/views/TermsView.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
    },
  ],
  scrollBehavior() {
    return { top: 0 }
  },
})

// Onboarding guard — runs on every navigation
// The user store is imported lazily to avoid circular deps
const ONBOARDING_ROUTES = ['profile-setup', 'identity', 'player-prefs', 'callback', 'not-found', 'free-agents', 'admin']

router.beforeEach(async (to) => {
  // Skip guard for onboarding routes themselves and public routes
  if (ONBOARDING_ROUTES.includes(to.name)) return true

  // Lazy import store to avoid circular dependency
  const { useUserStore } = await import('@/stores/user')
  const userStore = useUserStore()

  // If store not loaded yet, wait for it
  if (!userStore.predUser && !userStore.loading && !userStore.error) return true

  // Wait for any in-flight fetch
  let attempts = 0
  while (userStore.loading && attempts < 20) {
    await new Promise(r => setTimeout(r, 100))
    attempts++
  }

  if (!userStore.predUser) return true  // not logged in, let auth0 handle it

  if (userStore.needsNameSetup) return { name: 'profile-setup' }
  // Prefs are optional — users can navigate freely. The Player Profile link
  // in the nav dropdown is how they reach it when ready.

  // Admin guard
  if (to.meta?.requiresAdmin && !userStore.predUser?.is_admin) {
    return { name: 'home' }
  }

  return true
})

export default router
