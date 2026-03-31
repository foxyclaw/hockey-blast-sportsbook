<template>
  <div>
    <!-- Hero -->
    <div class="text-center mb-8">
      <h1 class="text-3xl font-extrabold tracking-tight mb-2">
        🏒 <span class="text-primary">Blast</span> Picks
      </h1>
      <p class="text-base-content/60 text-sm">Pick tonight's games. Earn points. Rule the rink.</p>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap gap-3 mb-6 items-end">
      <div class="form-control w-full sm:w-auto">
        <label class="label py-1">
          <span class="label-text text-xs text-base-content/60">Filter by Org</span>
        </label>
        <select v-model="selectedOrg" class="select select-bordered select-sm w-full sm:w-48" @change="loadGames">
          <option :value="null">All Orgs</option>
          <option v-for="org in orgs" :key="org.id" :value="org.id">{{ org.name }}</option>
        </select>
      </div>
      <button @click="loadGames" class="btn btn-sm btn-outline btn-primary mt-5">
        <span v-if="loading" class="loading loading-spinner loading-xs"></span>
        Refresh
      </button>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading && !games.length" class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div v-for="i in 3" :key="i" class="card bg-base-200 shadow-md animate-pulse">
        <div class="card-body p-4 gap-3">
          <div class="h-4 bg-base-300 rounded w-1/3"></div>
          <div class="grid grid-cols-3 gap-3">
            <div class="h-10 bg-base-300 rounded"></div>
            <div class="h-6 bg-base-300 rounded w-8 justify-self-center"></div>
            <div class="h-10 bg-base-300 rounded"></div>
          </div>
          <div class="h-3 bg-base-300 rounded w-1/2"></div>
        </div>
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="alert alert-warning">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" />
      </svg>
      <div>
        <div class="font-bold text-sm">Could not load games</div>
        <div class="text-xs">{{ error }} — Is the Flask API running on port 5000?</div>
      </div>
      <button @click="loadGames" class="btn btn-sm btn-outline">Retry</button>
    </div>

    <!-- Empty state -->
    <div v-else-if="!loading && !games.length" class="text-center py-16 text-base-content/40">
      <div class="text-4xl mb-3">🧊</div>
      <div class="font-semibold">No upcoming games found</div>
      <div class="text-sm mt-1">Check back later or try a different filter.</div>
    </div>

    <!-- Games list -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <GameCard
        v-for="game in games"
        :key="game.game_id"
        :game="game"
        @pick="openPickModal"
      />

      <!-- Load more -->
      <div v-if="hasMore" class="text-center pt-2">
        <button @click="loadMore" class="btn btn-outline btn-sm" :disabled="loadingMore">
          <span v-if="loadingMore" class="loading loading-spinner loading-xs"></span>
          Load more games
        </button>
      </div>
    </div>

    <!-- Pick Modal -->
    <PickModal
      :game="selectedGame"
      :open="modalOpen"
      @close="closePickModal"
      @picked="onPicked"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import GameCard from '@/components/GameCard.vue'
import PickModal from '@/components/PickModal.vue'
import { publicClient, useApiClient } from '@/api/client'
import { useAuth0 } from '@auth0/auth0-vue'

const { isAuthenticated } = useAuth0()
const authApi = useApiClient()

const games = ref([])
const orgs = ref([])
const loading = ref(false)
const loadingMore = ref(false)
const error = ref(null)
const selectedOrg = ref(1)
const page = ref(1)
const total = ref(0)
const perPage = 20

// Use authenticated client when logged in so user_pick is included in response
function gamesClient() {
  return isAuthenticated.value ? authApi : publicClient
}

const selectedGame = ref(null)
const modalOpen = ref(false)

const hasMore = computed(() => games.value.length < total.value)

import { computed } from 'vue'

async function loadGames() {
  loading.value = true
  error.value = null
  page.value = 1
  try {
    const params = { page: 1, per_page: perPage }
    if (selectedOrg.value) params.org_id = selectedOrg.value
    const { data } = await gamesClient().get('/api/games', { params })
    games.value = data.games ?? data
    total.value = data.total ?? games.value.length
    // Extract unique orgs for filter
    if (!orgs.value.length) {
      const orgMap = {}
      games.value.forEach((g) => {
        if (g.org?.id && !orgMap[g.org.id]) orgMap[g.org.id] = g.org
      })
      orgs.value = Object.values(orgMap)
    }
  } catch (e) {
    error.value = e.response?.data?.message ?? e.message
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  loadingMore.value = true
  page.value++
  try {
    const params = { page: page.value, per_page: perPage }
    if (selectedOrg.value) params.org_id = selectedOrg.value
    const { data } = await gamesClient().get('/api/games', { params })
    games.value.push(...(data.games ?? data))
    total.value = data.total ?? games.value.length
  } catch (e) {
    page.value--
  } finally {
    loadingMore.value = false
  }
}

function openPickModal(game) {
  selectedGame.value = game
  modalOpen.value = true
}

function closePickModal() {
  modalOpen.value = false
  selectedGame.value = null
}

function onPicked({ gameId, teamId, confidence }) {
  // Update the game in the list to show the pick — use index splice to force reactivity
  const idx = games.value.findIndex((g) => g.game_id === gameId)
  if (idx !== -1) {
    games.value[idx] = {
      ...games.value[idx],
      user_pick: { picked_team_id: teamId, confidence: confidence ?? 1 },
    }
  }
  closePickModal()
}

onMounted(loadGames)
</script>
