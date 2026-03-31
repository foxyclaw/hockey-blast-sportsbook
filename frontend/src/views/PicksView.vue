<template>
  <div>
    <!-- Header -->
    <div class="mb-6">
      <h1 class="text-2xl font-extrabold tracking-tight">My Picks</h1>
      <p class="text-base-content/60 text-sm mt-1">Track your predictions and earned points.</p>
    </div>

    <!-- Filter tabs -->
    <div class="tabs tabs-boxed mb-6 w-fit">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab"
        :class="{ 'tab-active': activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
        <span v-if="tabCount(tab.key) !== null" class="badge badge-sm ml-1">{{ tabCount(tab.key) }}</span>
      </button>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading" class="space-y-4">
      <div v-for="i in 4" :key="i" class="card bg-base-200 shadow-md animate-pulse">
        <div class="card-body p-4 gap-3">
          <div class="h-4 bg-base-300 rounded w-1/3"></div>
          <div class="h-4 bg-base-300 rounded w-2/3"></div>
          <div class="h-4 bg-base-300 rounded w-1/2"></div>
        </div>
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="alert alert-warning">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" />
      </svg>
      <div>
        <div class="font-bold text-sm">Could not load picks</div>
        <div class="text-xs">{{ error }}</div>
      </div>
      <button @click="loadPicks" class="btn btn-sm btn-outline">Retry</button>
    </div>

    <!-- Empty state -->
    <div v-else-if="filteredPicks.length === 0" class="text-center py-16 text-base-content/40">
      <div class="text-4xl mb-3">🎯</div>
      <div class="font-semibold">No picks {{ activeTab !== 'all' ? `in "${tabs.find(t=>t.key===activeTab)?.label}"` : '' }}</div>
      <div class="text-sm mt-1">
        <template v-if="activeTab === 'all'">
          Head to <RouterLink to="/" class="link link-primary">Games</RouterLink> and make your first pick!
        </template>
        <template v-else>Try the "All" tab to see all picks.</template>
      </div>
    </div>

    <!-- Picks list -->
    <div v-else class="space-y-4">
      <div
        v-for="pick in filteredPicks"
        :key="pick.id"
        class="card bg-base-200 shadow-md"
      >
        <div class="card-body p-4">
          <div class="flex items-start justify-between gap-2 flex-wrap">
            <!-- Game info -->
            <div class="flex-1 min-w-0">
              <div class="font-semibold text-sm truncate">
                {{ pick.home_team_name ?? 'Home' }} vs {{ pick.away_team_name ?? 'Away' }}
              </div>
              <div class="text-xs text-base-content/50 mt-0.5">
                {{ formatDate(pick.game_scheduled_start) }}
              </div>
            </div>

            <!-- Status badge -->
            <span
              class="badge badge-sm shrink-0"
              :class="pick.status === 'graded' ? ((pick.points_earned ?? 0) > 0 ? 'badge-success' : 'badge-error') : pick.status === 'live' ? 'badge-warning' : 'badge-ghost'"
            >
              <span v-if="pick.status === 'live'" class="inline-block w-2 h-2 rounded-full bg-error animate-pulse mr-1"></span>
              {{ pick.status === 'graded' ? ((pick.points_earned ?? 0) > 0 ? `+${pick.points_earned} pts` : 'No pts') : pick.status === 'live' ? 'Live' : 'Pending' }}
            </span>
          </div>

          <div class="flex items-center gap-3 mt-2 flex-wrap">
            <!-- Team picked -->
            <div class="flex items-center gap-2">
              <span class="text-xs text-base-content/60">Picked:</span>
              <span class="font-semibold text-sm text-primary">{{ pick.picked_team_name ?? pick.picked_team_id }}</span>
            </div>

            <!-- Confidence -->
            <div class="badge badge-outline badge-primary text-xs font-mono">
              {{ pick.confidence ?? 1 }}x
            </div>

            <!-- Wager -->
            <div v-if="pick.wager" class="text-xs text-base-content/60">
              💰 {{ pick.wager }} pts wager
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useApiClient } from '@/api/client'

const api = useApiClient()

const picks = ref([])
const loading = ref(false)
const error = ref(null)
const activeTab = ref('current')

const tabs = [
  { key: 'current', label: 'Current' },
  { key: 'past', label: 'Past' },
]

const filteredPicks = computed(() => {
  if (activeTab.value === 'current') return picks.value.filter(p => p.status !== 'graded')
  return picks.value.filter(p => p.status === 'graded')
})

function tabCount(key) {
  if (key === 'current') return picks.value.filter(p => p.status !== 'graded').length || null
  return picks.value.filter(p => p.status === 'graded').length || null
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  })
}

async function loadPicks() {
  loading.value = true
  error.value = null
  try {
    const { data } = await api.get('/api/picks/mine')
    picks.value = data.picks ?? data
  } catch (e) {
    error.value = e.response?.data?.message ?? e.message
  } finally {
    loading.value = false
  }
}

onMounted(loadPicks)
</script>
