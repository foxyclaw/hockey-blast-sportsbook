<template>
  <div class="container mx-auto px-4 py-6 max-w-2xl">
    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-16">
      <span class="loading loading-spinner loading-lg text-primary"></span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="alert alert-error">
      <span>{{ error }}</span>
    </div>

    <template v-else-if="standings">
      <!-- Header -->
      <div class="mb-6">
        <h1 class="text-2xl font-bold text-primary">{{ standings.league_name }}</h1>
        <p class="text-base-content/60 text-sm mt-1">Leaderboard</p>
      </div>

      <!-- Empty state -->
      <div v-if="!standings.standings?.length" class="text-center py-16 text-base-content/50">
        <div class="text-5xl mb-4">🏒</div>
        <p class="text-lg font-medium">No picks yet</p>
        <p class="text-sm mt-1">Make some picks to appear on the leaderboard!</p>
        <router-link to="/" class="btn btn-primary btn-sm mt-4">Browse Games</router-link>
      </div>

      <!-- Standings table -->
      <div v-else class="card bg-base-200 shadow-xl overflow-hidden">
        <table class="table table-zebra w-full">
          <thead>
            <tr class="text-base-content/70 text-xs uppercase">
              <th class="w-12 text-center">#</th>
              <th>Player</th>
              <th class="text-right">Points</th>
              <th class="text-right">💰 Balance</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(entry, idx) in standings.standings"
              :key="entry.user_id"
              :class="[
                'transition-colors',
                isCurrentUser(entry.user_id) ? 'bg-primary/20 font-semibold' : ''
              ]"
            >
              <!-- Rank -->
              <td class="text-center">
                <span v-if="idx === 0" class="text-xl">🥇</span>
                <span v-else-if="idx === 1" class="text-xl">🥈</span>
                <span v-else-if="idx === 2" class="text-xl">🥉</span>
                <span v-else class="text-base-content/60">{{ idx + 1 }}</span>
              </td>

              <!-- Player -->
              <td>
                <div class="flex items-center gap-2">
                  <div class="avatar placeholder">
                    <div class="w-8 h-8 rounded-full bg-primary/30 text-primary text-xs flex items-center justify-center">
                      {{ initials(entry.display_name) }}
                    </div>
                  </div>
                  <div>
                    <div class="font-medium">{{ entry.display_name }}</div>
                    <div v-if="isCurrentUser(entry.user_id)" class="text-xs text-primary">You</div>
                  </div>
                </div>
              </td>

              <!-- Points -->
              <td class="text-right">
                <span class="font-mono font-bold text-accent">{{ entry.total_points ?? 0 }}</span>
                <span class="text-xs text-base-content/50 ml-1">pts</span>
              </td>

              <!-- Balance -->
              <td class="text-right">
                <span class="font-mono">{{ formatBalance(entry.balance) }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Last updated -->
      <p v-if="standings.last_updated_at" class="text-center text-xs text-base-content/40 mt-4">
        Updated {{ timeAgo(standings.last_updated_at) }}
      </p>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuth0 } from '@auth0/auth0-vue'
import { useApiClient } from "@/api/client"
const api = useApiClient()

const route = useRoute()
const { user } = useAuth0()

const standings = ref(null)
const loading = ref(true)
const error = ref(null)

onMounted(async () => {
  try {
    const res = await api.get(`/standings/${route.params.id}`)
    standings.value = res.data
  } catch (e) {
    error.value = e.response?.data?.message || 'Failed to load standings'
  } finally {
    loading.value = false
  }
})

function isCurrentUser(userId) {
  // Match by user sub embedded in JWT — best effort
  return false // TODO: wire up after /auth/me is in user store
}

function initials(name) {
  if (!name) return '?'
  return name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
}

function formatBalance(bal) {
  if (bal == null) return '—'
  return Number(bal).toLocaleString()
}

function timeAgo(iso) {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  return `${Math.floor(mins / 60)}h ago`
}
</script>
