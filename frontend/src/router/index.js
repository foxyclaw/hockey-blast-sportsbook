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
      path: '/identity',
      name: 'identity',
      component: () => import('@/views/IdentityView.vue'),
      beforeEnter: authGuard,
    },
    {
      path: '/callback',
      name: 'callback',
      component: () => import('@/views/CallbackView.vue'),
    },
    {
      // Catch-all 404
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
    },
  ],
  scrollBehavior() {
    return { top: 0 }
  },
})

export default router
