<template>
  <div>
    <!-- Header -->
    <div class="mb-6">
      <h1 class="text-2xl font-extrabold tracking-tight">Groups</h1>
      <p class="text-base-content/60 text-sm mt-1">Compete with friends. Create or join a league.</p>
    </div>

    <!-- Action forms -->
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
      <!-- Create League -->
      <div class="card bg-base-200 shadow-md">
        <div class="card-body p-4">
          <h2 class="card-title text-base mb-2">🏆 Create a League</h2>
          <form @submit.prevent="createLeague" class="space-y-3">
            <div class="form-control">
              <label class="label py-1">
                <span class="label-text text-xs">League Name</span>
              </label>
              <input
                v-model="createForm.name"
                type="text"
                placeholder="The Puck Stops Here"
                class="input input-bordered input-sm"
                required
              />
            </div>
            <div class="form-control">
              <label class="label py-1">
                <span class="label-text text-xs">Season Label</span>
              </label>
              <input
                v-model="createForm.season_label"
                type="text"
                placeholder="2024-25"
                class="input input-bordered input-sm"
              />
            </div>
            <div class="form-control">
              <label class="label py-1">
                <span class="label-text text-xs">Season Start</span>
              </label>
              <input
                v-model="createForm.season_starts_at"
                type="datetime-local"
                class="input input-bordered input-sm"
              />
            </div>
            <div class="grid grid-cols-2 gap-2">
              <div class="form-control">
                <label class="label py-1">
                  <span class="label-text text-xs">Draft Opens</span>
                </label>
                <input
                  v-model="createForm.draft_opens_at"
                  type="datetime-local"
                  class="input input-bordered input-sm"
                />
              </div>
              <div class="form-control">
                <label class="label py-1">
                  <span class="label-text text-xs">Draft Closes</span>
                </label>
                <input
                  v-model="createForm.draft_closes_at"
                  type="datetime-local"
                  class="input input-bordered input-sm"
                />
              </div>
            </div>
            <button type="submit" class="btn btn-primary btn-sm w-full" :disabled="creating">
              <span v-if="creating" class="loading loading-spinner loading-xs"></span>
              Create League
            </button>
            <div v-if="createError" class="text-error text-xs">{{ createError }}</div>
          </form>
        </div>
      </div>

      <!-- Join League -->
      <div class="card bg-base-200 shadow-md">
        <div class="card-body p-4">
          <h2 class="card-title text-base mb-2">🔑 Join a League</h2>
          <form @submit.prevent="joinLeague" class="space-y-3">
            <div class="form-control">
              <label class="label py-1">
                <span class="label-text text-xs">Join Code</span>
              </label>
              <input
                v-model="joinForm.join_code"
                type="text"
                placeholder="ABC-123"
                class="input input-bordered input-sm font-mono uppercase"
                required
              />
            </div>
            <button type="submit" class="btn btn-secondary btn-sm w-full mt-8" :disabled="joining">
              <span v-if="joining" class="loading loading-spinner loading-xs"></span>
              Join League
            </button>
            <div v-if="joinError" class="text-error text-xs">{{ joinError }}</div>
          </form>
        </div>
      </div>
    </div>

    <!-- My Groups -->
    <div>
      <h2 class="text-lg font-bold mb-4">My Groups</h2>

      <!-- Loading -->
      <div v-if="loading" class="space-y-3">
        <div v-for="i in 2" :key="i" class="card bg-base-200 animate-pulse">
          <div class="card-body p-4 gap-3">
            <div class="h-5 bg-base-300 rounded w-1/2"></div>
            <div class="h-4 bg-base-300 rounded w-1/3"></div>
          </div>
        </div>
      </div>

      <!-- Error -->
      <div v-else-if="leaguesError" class="alert alert-warning">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" />
        </svg>
        <span class="text-sm">{{ leaguesError }}</span>
        <button @click="loadLeagues" class="btn btn-sm btn-outline">Retry</button>
      </div>

      <!-- Empty state -->
      <div v-else-if="!loading && leagues.length === 0" class="text-center py-12 text-base-content/40">
        <div class="text-4xl mb-3">🏒</div>
        <div class="font-semibold">No groups yet</div>
        <div class="text-sm mt-1">Create one or ask a friend for a join code.</div>
      </div>

      <!-- League cards -->
      <div v-else class="space-y-3">
        <div
          v-for="league in leagues"
          :key="league.id"
          class="card bg-base-200 shadow-md hover:shadow-lg transition-shadow cursor-pointer"
        >
          <div class="card-body p-4">
            <div class="flex items-center justify-between gap-2 flex-wrap">
              <div class="flex-1 min-w-0">
                <div class="font-semibold truncate">{{ league.name }}</div>
                <div v-if="league.season_label" class="text-xs text-base-content/50 mt-0.5">
                  📅 {{ league.season_label }}
                </div>
              </div>
              <RouterLink :to="`/leagues/${league.id}`" class="btn btn-outline btn-sm">
                Standings →
              </RouterLink>
            </div>

            <div class="flex items-center gap-3 mt-2 flex-wrap">
              <!-- Join code -->
              <div v-if="league.join_code" class="flex items-center gap-2">
                <span class="text-xs text-base-content/60">Code:</span>
                <code class="font-mono text-sm bg-base-300 px-2 py-0.5 rounded">{{ league.join_code }}</code>
                <button
                  class="btn btn-ghost btn-xs"
                  :title="copied === league.id ? 'Copied!' : 'Copy code'"
                  @click="copyCode(league.join_code, league.id)"
                >
                  <span v-if="copied === league.id">✅</span>
                  <span v-else>📋</span>
                </button>
              </div>

              <!-- Member count -->
              <div v-if="league.member_count != null" class="text-xs text-base-content/60">
                👥 {{ league.member_count }} {{ league.member_count === 1 ? 'member' : 'members' }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useApiClient } from '@/api/client'
import { useAuth0 } from '@auth0/auth0-vue'

const api = useApiClient()

const { isAuthenticated, loginWithRedirect } = useAuth0()

const leagues = ref([])
const loading = ref(false)
const leaguesError = ref(null)

const createForm = ref({ name: '', season_label: '', season_starts_at: '', draft_opens_at: '', draft_closes_at: '' })
const creating = ref(false)
const createError = ref(null)

const joinForm = ref({ join_code: '' })
const joining = ref(false)
const joinError = ref(null)

const copied = ref(null)

async function loadLeagues() {
  loading.value = true
  leaguesError.value = null
  try {
    const { data } = await api.get('/api/leagues/mine')
    leagues.value = data.leagues ?? data
  } catch (e) {
    leaguesError.value = e.response?.data?.message ?? e.message
  } finally {
    loading.value = false
  }
}

async function createLeague() {
  creating.value = true
  createError.value = null
  try {
    const { data } = await api.post('/api/leagues', {
      name: createForm.value.name,
      season_label: createForm.value.season_label || undefined,
      season_starts_at: createForm.value.season_starts_at || undefined,
      draft_opens_at: createForm.value.draft_opens_at || undefined,
      draft_closes_at: createForm.value.draft_closes_at || undefined,
    })
    const newLeague = data.league ?? data
    leagues.value.unshift(newLeague)
    createForm.value = { name: '', season_label: '', season_starts_at: '', draft_opens_at: '', draft_closes_at: '' }
  } catch (e) {
    createError.value = e.response?.data?.message ?? e.message
  } finally {
    creating.value = false
  }
}

function requireLogin() {
  localStorage.setItem('auth_return_to', window.location.pathname + window.location.search)
  loginWithRedirect()
}

async function joinLeague() {
  if (!isAuthenticated.value) {
    requireLogin()
    return
  }
  joining.value = true
  joinError.value = null
  try {
    const { data } = await api.post('/api/leagues/join', {
      join_code: joinForm.value.join_code.trim().toUpperCase(),
    })
    const joined = data.league ?? data
    if (joined && !leagues.value.find((l) => l.id === joined.id)) {
      leagues.value.push(joined)
    }
    joinForm.value = { join_code: '' }
  } catch (e) {
    if (e.response?.status === 401) {
      requireLogin()
      return
    }
    joinError.value = e.response?.data?.message ?? e.message
  } finally {
    joining.value = false
  }
}

async function copyCode(code, leagueId) {
  try {
    await navigator.clipboard.writeText(code)
    copied.value = leagueId
    setTimeout(() => {
      if (copied.value === leagueId) copied.value = null
    }, 2000)
  } catch {
    // fallback: do nothing
  }
}

onMounted(loadLeagues)
</script>
