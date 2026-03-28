<template>
  <div class="navbar bg-base-300 shadow-lg sticky top-0 z-50 border-b border-base-content/10 px-2">
    <div class="navbar-start w-auto shrink-0 gap-1 flex-none">
      <RouterLink to="/" class="btn btn-ghost text-xl font-bold tracking-tight">
        🏒 <span class="text-primary font-bold">HB</span>
      </RouterLink>
      <span class="text-base-content/20">|</span>
      <a href="https://hockey-blast.com" class="btn btn-ghost font-bold tracking-tight text-sm">
        <span class="text-base-content/40">Stats</span>
      </a>

    </div>

    <div class="navbar-center hidden sm:flex flex-1">
      <ul class="menu menu-horizontal px-1 gap-1">
        <li>
          <RouterLink to="/" class="rounded-lg text-sm font-medium" active-class="bg-primary/20 text-primary">
            Games
          </RouterLink>
        </li>
        <li v-if="isFullyAuthenticated">
          <RouterLink to="/picks" class="rounded-lg text-sm font-medium" active-class="bg-primary/20 text-primary">
            My Picks
          </RouterLink>
        </li>
        <li>
          <RouterLink to="/fantasy" class="rounded-lg text-sm font-medium" active-class="bg-primary/20 text-primary">
            Fantasy
          </RouterLink>
        </li>
        <li v-if="isFullyAuthenticated">
          <RouterLink to="/my-fantasy" class="rounded-lg text-sm font-medium" active-class="bg-primary/20 text-primary">
            My Leagues
          </RouterLink>
        </li>
        <li v-if="isFullyAuthenticated && predUser?.is_admin">
          <RouterLink to="/admin" class="rounded-lg text-sm font-medium" active-class="bg-primary/20 text-primary">
            🛡️ Admin
          </RouterLink>
        </li>
        <li>
          <button @click="helpButtonRef?.open()" class="rounded-lg text-sm font-bold" title="Help / Feedback">?</button>
        </li>
      </ul>
    </div>
    <HelpButton ref="helpButtonRef" />

    <div class="navbar-end gap-2 flex-1 justify-end">
      <!-- Balance badge -->
      <div v-if="isFullyAuthenticated && !isLoading" class="badge badge-outline badge-primary font-mono text-xs hidden sm:flex">
        💰 {{ balance.toLocaleString() }} pts
      </div>

      <!-- Notification bell (authenticated users only) -->
      <div v-if="isFullyAuthenticated && !isLoading" class="relative">
        <button @click="toggleNotifications" class="btn btn-ghost btn-circle btn-sm relative">
          <span class="text-lg">🔔</span>
          <span
            v-if="unreadCount > 0"
            class="absolute -top-1 -right-1 bg-error text-white text-xs rounded-full w-4 h-4 flex items-center justify-center"
          >
            {{ unreadCount > 9 ? '9+' : unreadCount }}
          </span>
        </button>
        <!-- Click outside overlay -->
        <div v-if="showNotifications" class="fixed inset-0 z-10" @click="showNotifications = false"></div>
        <!-- Dropdown -->
        <div
          v-if="showNotifications"
          class="absolute right-0 top-12 w-80 bg-base-200 rounded-box shadow-xl z-50 border border-base-content/10"
        >
          <div class="p-3 border-b border-base-content/10 flex justify-between">
            <span class="font-semibold text-sm">Notifications</span>
            <button v-if="notifications.length" @click="markAllRead" class="text-xs link">Mark all read</button>
          </div>
          <div class="max-h-80 overflow-y-auto">
            <div v-if="!notifications.length" class="p-4 text-center text-base-content/50 text-sm">
              No notifications yet
            </div>
            <button
              v-for="n in notifications"
              :key="n.id"
              class="w-full text-left p-3 border-b border-base-content/5 hover:bg-base-300 cursor-pointer block"
              :class="{ 'opacity-60': n.is_read }"
              @click.stop="openNotification(n)"
            >
              <div class="text-sm font-medium">{{ n.title }}</div>
              <div v-if="n.body" class="text-xs text-base-content/60 mt-0.5">{{ n.body }}</div>
              <div class="text-xs text-base-content/40 mt-1">{{ timeAgo(n.created_at) }}</div>
            </button>
          </div>
        </div>
      </div>

      <!-- Auth button -->
      <div v-if="isLoading">
        <span class="loading loading-spinner loading-sm text-primary"></span>
      </div>
      <div v-else-if="isFullyAuthenticated" class="dropdown dropdown-end">
        <div tabindex="0" role="button" class="btn btn-ghost btn-circle avatar">
          <div class="w-9 rounded-full ring ring-primary ring-offset-base-100 ring-offset-1">
            <img v-if="user?.picture" :src="user.picture" :alt="user.name" />
            <div v-else class="bg-primary text-primary-content w-9 h-9 flex items-center justify-center rounded-full text-sm font-bold">
              {{ user?.name?.[0] ?? '?' }}
            </div>
          </div>
        </div>
        <!-- Avatar dropdown: account only -->
        <ul tabindex="0" class="mt-3 z-[1] p-2 shadow menu menu-sm dropdown-content bg-base-200 rounded-box w-52">
          <li class="menu-title px-3 py-1">
            <span class="text-xs opacity-60">{{ user?.email }}</span>
          </li>
          <li><RouterLink to="/player-prefs">Player Profile</RouterLink></li>
          <li v-if="predUser?.is_admin"><RouterLink to="/admin">🛡️ Admin</RouterLink></li>
          <li><hr class="my-1 opacity-20" /></li>
          <li>
            <button @click="logout({ logoutParams: { returnTo: window.location.origin } })" class="text-error">
              Sign Out
            </button>
          </li>
        </ul>
      </div>

      <!-- Mobile hamburger: full site nav -->
      <div class="dropdown dropdown-end sm:hidden">
        <label tabindex="0" class="btn btn-ghost btn-sm">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </label>
        <ul tabindex="0" class="menu menu-sm dropdown-content mt-3 z-[1] p-2 shadow bg-base-200 rounded-box w-52">
          <li><RouterLink to="/">🏒 Games</RouterLink></li>
          <li><RouterLink to="/fantasy">🏆 Fantasy</RouterLink></li>
          <li v-if="isFullyAuthenticated"><RouterLink to="/my-fantasy">⭐ My Leagues</RouterLink></li>
          <li v-if="isFullyAuthenticated"><RouterLink to="/picks">🎯 My Picks</RouterLink></li>
          <li v-if="isFullyAuthenticated"><hr class="my-1 opacity-20" /></li>
          <li v-if="isFullyAuthenticated"><RouterLink to="/player-prefs">👤 Player Profile</RouterLink></li>
          <li v-if="isFullyAuthenticated && predUser?.is_admin"><RouterLink to="/admin">🛡️ Admin</RouterLink></li>
          <li v-if="!isFullyAuthenticated"><hr class="my-1 opacity-20" /></li>
          <li v-if="!isFullyAuthenticated"><button @click="doLogin()" class="text-primary font-medium">Sign In</button></li>
        </ul>
      </div>
      <button v-if="!isFullyAuthenticated && !isLoading" @click="doLogin()" class="btn btn-primary btn-sm sm:flex hidden" :disabled="loginInProgress">
        <span v-if="loginInProgress" class="loading loading-spinner loading-xs"></span>
        Sign In
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth0 } from '@auth0/auth0-vue'
import { useUserStore } from '@/stores/user'
import { useApiClient } from '@/api/client'
import HelpButton from '@/components/HelpButton.vue'

const { isAuthenticated, isLoading, user, loginWithRedirect, logout } = useAuth0()
const userStore = useUserStore()
// Only treat as truly logged in if Auth0 says so AND the backend confirmed the token
const isFullyAuthenticated = computed(() => isAuthenticated.value && userStore.predUser !== null)
const predUser = computed(() => userStore.predUser)
const router = useRouter()
const loginInProgress = ref(false)
const helpButtonRef = ref(null)

const balance = computed(() => userStore.balance)
const api = useApiClient()

// ── Notifications ──────────────────────────────────────────────────────────
const notifications = ref([])
const unreadCount = ref(0)
const showNotifications = ref(false)

async function loadNotifications() {
  if (!isAuthenticated.value) return
  try {
    const { data } = await api.get('/api/notifications')
    notifications.value = data.notifications || []
    unreadCount.value = notifications.value.filter(n => !n.is_read).length
  } catch {
    // silently ignore — bell just shows 0
  }
}

function toggleNotifications() {
  showNotifications.value = !showNotifications.value
  if (showNotifications.value) loadNotifications()
}

async function markAllRead() {
  for (const n of [...notifications.value]) {
    await api.post(`/api/notifications/${n.id}/read`).catch(() => {})
  }
  notifications.value = []
  unreadCount.value = 0
  showNotifications.value = false
}

function openNotification(n) {
  api.post(`/api/notifications/${n.id}/read`).catch(() => {})
  // Remove from list immediately — delete on read
  notifications.value = notifications.value.filter(x => x.id !== n.id)
  unreadCount.value = Math.max(0, unreadCount.value - 1)
  showNotifications.value = false
  if (n.link) {
    setTimeout(() => router.push(n.link), 100)
  }
}

function timeAgo(iso) {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  if (mins < 1440) return `${Math.floor(mins / 60)}h ago`
  return `${Math.floor(mins / 1440)}d ago`
}

// Load notifications when user logs in
// Poll notifications every 30s when user is logged in
let _notifInterval = null
onMounted(() => {
  if (isAuthenticated.value) {
    _notifInterval = setInterval(loadNotifications, 30000)
  }
})
onUnmounted(() => {
  if (_notifInterval) clearInterval(_notifInterval)
})
watch(isAuthenticated, (v) => {
  if (v) {
    loadNotifications()
    if (!_notifInterval) _notifInterval = setInterval(loadNotifications, 30000)
  } else {
    if (_notifInterval) { clearInterval(_notifInterval); _notifInterval = null }
  }
})

// ── Login ──────────────────────────────────────────────────────────────────
async function doLogin() {
  await loginWithRedirect()
}
</script>
