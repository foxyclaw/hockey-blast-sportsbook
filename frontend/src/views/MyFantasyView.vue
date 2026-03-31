<template>
  <div class="max-w-4xl mx-auto px-4 py-6">

    <!-- Not authenticated -->
    <div v-if="!isAuthenticated" class="text-center py-20">
      <div class="text-5xl mb-4">🔒</div>
      <h2 class="text-xl font-bold mb-2">Sign in to see your leagues</h2>
      <p class="text-base-content/50 text-sm mb-6">Your personal fantasy dashboard is just a login away.</p>
      <button class="btn btn-primary" @click="loginWithRedirect()">Sign In</button>
    </div>

    <template v-else>
      <!-- Your turn banner -->
      <div
        v-if="hasYourTurn"
        class="rounded-xl bg-warning/20 border-2 border-warning/60 px-5 py-4 mb-6 flex items-center gap-4 animate-pulse"
      >
        <span class="text-3xl">🏒</span>
        <div>
          <div class="font-extrabold text-base-content text-lg leading-tight">It's your turn to pick!</div>
          <div class="text-sm text-base-content/60 mt-0.5">Head to your league and make your draft selection.</div>
        </div>
      </div>

      <!-- Header -->
      <div class="mb-6">
        <h1 class="text-2xl font-extrabold tracking-tight">🏒 My Leagues</h1>
        <p class="text-base-content/60 text-sm mt-1">Leagues you've joined — your personal fantasy dashboard.</p>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="flex justify-center py-12">
        <span class="loading loading-spinner loading-lg text-primary"></span>
      </div>

      <!-- Empty state -->
      <div v-else-if="myLeagues.length === 0" class="text-center py-16 text-base-content/40">
        <div class="text-5xl mb-3">🏒</div>
        <p class="font-semibold mb-1">You haven't joined any leagues yet.</p>
        <p class="text-sm mb-5">Browse available leagues and jump in!</p>
        <RouterLink to="/fantasy" class="btn btn-primary btn-sm">Browse Fantasy Leagues →</RouterLink>
      </div>

      <!-- Grouped leagues -->
      <div v-else class="space-y-6">
        <div v-for="group in groupedLeagues" :key="group.label">
          <h2 class="text-sm font-semibold text-base-content/50 uppercase tracking-wider mb-3">
            {{ group.label }}
          </h2>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div
              v-for="league in group.leagues"
              :key="league.id"
              class="card bg-base-200 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
              @click="$router.push(`/fantasy/${league.id}`)"
            >
              <div class="card-body p-4">
                <div class="flex items-start justify-between gap-2">
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-2">
                      <h3 class="font-bold text-base">{{ league.name }}</h3>
                      <span v-if="league.is_private" class="badge badge-xs badge-neutral gap-1">🔒 Private</span>
                    </div>
                    <p class="text-xs text-base-content/50 flex flex-wrap gap-x-2 mt-0.5">
                      <span v-if="league.org_name">🏢 {{ league.org_name }}</span>
                      <span v-if="league.hb_league_name">🏒 {{ league.hb_league_name }}</span>
                      <span>📊 {{ league.level_name }}</span>
                      <span v-if="league.season_label">📅 {{ league.season_label }}</span>
                    </p>
                  </div>
                  <span class="badge badge-sm shrink-0" :class="statusBadgeClass(league.status)">
                    {{ statusLabel(league.status) }}
                  </span>
                </div>
                <div class="flex items-center gap-3 mt-3 text-xs text-base-content/60">
                  <span>👥 {{ league.manager_count }} / {{ league.max_managers }} managers</span>
                  <span v-if="league.is_your_turn" class="badge badge-xs badge-warning animate-pulse">⚡ Your Turn!</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuth0 } from '@auth0/auth0-vue'
import { useApiClient } from '@/api/client'

const { isAuthenticated, loginWithRedirect } = useAuth0()
const api = useApiClient()

const leagues = ref([])
const loading = ref(true)

const STATUS_ORDER = ['active', 'drafting', 'draft_open', 'forming', 'completed']
const STATUS_LABELS = {
  forming: 'Forming',
  draft_open: 'Draft Open',
  drafting: 'Drafting',
  active: 'Active',
  completed: 'Completed',
}

function statusLabel(s) { return STATUS_LABELS[s] || s }

function statusBadgeClass(s) {
  return {
    forming: 'badge-info',
    draft_open: 'badge-warning',
    drafting: 'badge-warning',
    active: 'badge-success',
    completed: 'badge-neutral',
  }[s] || 'badge-ghost'
}

const myLeagues = computed(() => leagues.value.filter(l => l.is_member))

const hasYourTurn = computed(() => myLeagues.value.some(l => l.is_your_turn))

const groupedLeagues = computed(() => {
  const groups = {}
  for (const league of myLeagues.value) {
    const label = STATUS_LABELS[league.status] || league.status
    if (!groups[label]) groups[label] = []
    groups[label].push(league)
  }
  return Object.entries(groups)
    .map(([label, ls]) => ({ label, leagues: ls.slice().sort((a, b) => (a.name || '').localeCompare(b.name || '')) }))
    .sort((a, b) => {
      const aStatus = myLeagues.value.find(l => STATUS_LABELS[l.status] === a.label)?.status || ''
      const bStatus = myLeagues.value.find(l => STATUS_LABELS[l.status] === b.label)?.status || ''
      return STATUS_ORDER.indexOf(aStatus) - STATUS_ORDER.indexOf(bStatus)
    })
})

async function loadLeagues() {
  if (!isAuthenticated.value) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const { data } = await api.get('/api/fantasy/leagues')
    leagues.value = data.leagues || []
  } catch {
    leagues.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadLeagues()
})
</script>
