<template>
  <div class="max-w-4xl mx-auto px-4 py-6">
    <!-- Header -->
    <div class="mb-6 flex items-start justify-between flex-wrap gap-4">
      <div>
        <h1 class="text-2xl font-extrabold tracking-tight">🏒 Fantasy Hockey</h1>
        <p class="text-base-content/60 text-sm mt-1">Draft skaters, goalies, and refs — score points, win glory (and maybe cash). Set up a private league for your crew.</p>
      </div>
      <div class="flex gap-2">
        <button class="btn btn-outline btn-sm" @click="showJoinCodeEntry = true">
          🔑 Join with Code
        </button>
        <button class="btn btn-primary btn-sm" @click="openCreateModal">
          + Create League
        </button>
      </div>
    </div>

    <!-- Status groups -->
    <div v-if="loading" class="flex justify-center py-12">
      <span class="loading loading-spinner loading-lg text-primary"></span>
    </div>

    <div v-else-if="leagues.length === 0" class="text-center py-16 text-base-content/40">
      <div class="text-5xl mb-3">🏒</div>
      <p>No leagues yet. Create one to get started!</p>
    </div>

    <div v-else class="space-y-6">
      <div v-for="group in groupedLeagues" :key="group.label">
        <h2 class="text-sm font-semibold text-base-content/50 uppercase tracking-wider mb-3">
          {{ group.label }}
        </h2>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div
            v-for="league in group.leagues"
            :key="league.id"
            class="card bg-base-200 shadow-sm hover:shadow-md transition-shadow"
          >
            <div class="card-body p-4">
              <div class="flex items-start justify-between gap-2 cursor-pointer" @click="$router.push(`/fantasy/${league.id}`)">
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <h3 class="font-bold text-base">{{ league.name }}</h3>
                    <span v-if="league.is_private" class="badge badge-xs badge-neutral gap-1">🔒 Private</span>
                  </div>
                  <p class="text-xs text-base-content/50 flex flex-wrap gap-x-2">
                    <span v-if="league.org_name">🏢 {{ league.org_name }}</span>
                    <span v-if="league.hb_league_name">🏒 {{ league.hb_league_name }}</span>
                    <span>📊 {{ league.level_name }}</span>
                    <span v-if="league.season_label">📅 {{ league.season_label }}</span>
                  </p>
                </div>
                <span class="badge badge-sm shrink-0" :class="statusBadgeClass(league.status)">
                  {{ statusLabel(league.status) }}
                </span>
                <span v-if="league.has_live_game" class="inline-flex items-center gap-1 badge badge-xs badge-success animate-pulse ml-1">
                  <span class="w-1.5 h-1.5 rounded-full bg-white inline-block"></span>LIVE
                </span>
              </div>
              <div class="flex items-center gap-4 mt-3 text-xs text-base-content/60">
                <span>👥 {{ league.manager_count }} / {{ league.max_managers }} managers</span>
                <span v-if="league.is_your_turn" class="badge badge-xs badge-warning animate-pulse">⚡ Your Turn!</span>
                <span v-else-if="league.is_member" class="badge badge-xs badge-success">Joined</span>
              </div>
              <!-- Join button / code input for non-members in forming status -->
              <div v-if="!league.is_member && ['forming', 'draft_open'].includes(league.status)" class="mt-3">
                <div v-if="!league.is_private">
                  <button class="btn btn-xs btn-outline btn-primary" @click="$router.push(`/fantasy/${league.id}`)">Join →</button>
                </div>
                <div v-else>
                  <button class="btn btn-xs btn-outline btn-neutral" @click="startJoinPrivate(league)">Enter Code to Join</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Private join code prompt modal -->
    <div v-if="showPrivateJoinModal" class="modal modal-open">
      <div class="modal-box max-w-sm">
        <h3 class="font-bold text-lg mb-2">Join Private League</h3>
        <p class="text-sm text-base-content/60 mb-4">Enter the invite code to join <strong>{{ privateJoinLeague?.name }}</strong>.</p>
        <form @submit.prevent="goToPrivateLeague" class="space-y-3">
          <div class="form-control">
            <input
              v-model="privateJoinCode"
              type="text"
              placeholder="e.g. X7K2M9"
              class="input input-bordered input-sm uppercase"
              maxlength="6"
              required
            />
          </div>
          <div v-if="privateJoinError" class="alert alert-error text-sm py-2">{{ privateJoinError }}</div>
          <div class="modal-action">
            <button type="button" class="btn btn-ghost btn-sm" @click="showPrivateJoinModal = false">Cancel</button>
            <button type="submit" class="btn btn-primary btn-sm">Continue →</button>
          </div>
        </form>
      </div>
      <div class="modal-backdrop" @click="showPrivateJoinModal = false"></div>
    </div>

    <!-- Join Private League by Code Modal -->
    <div v-if="showJoinCodeEntry" class="modal modal-open">
      <div class="modal-box max-w-sm">
        <h3 class="font-bold text-lg mb-2">Join Private League</h3>
        <p class="text-sm text-base-content/60 mb-4">Enter the invite code you received from the league creator.</p>
        <form @submit.prevent="submitJoinCode" class="space-y-3">
          <div class="form-control">
            <input
              v-model="joinCodeEntry"
              type="text"
              placeholder="e.g. X7K2M9"
              class="input input-bordered input-sm uppercase tracking-widest text-center text-lg font-mono"
              maxlength="6"
              required
              autofocus
            />
          </div>
          <div v-if="joinCodeError" class="alert alert-error text-sm py-2">{{ joinCodeError }}</div>
          <div class="modal-action">
            <button type="button" class="btn btn-ghost btn-sm" @click="showJoinCodeEntry = false; joinCodeEntry = ''; joinCodeError = ''">Cancel</button>
            <button type="submit" class="btn btn-primary btn-sm" :disabled="joinCodeEntry.length < 6">Join →</button>
          </div>
        </form>
      </div>
      <div class="modal-backdrop" @click="showJoinCodeEntry = false; joinCodeEntry = ''; joinCodeError = ''"></div>
    </div>

    <!-- Create League Modal -->
    <div v-if="showCreateModal" :key="createModalKey" class="modal modal-open">
      <div class="modal-box max-w-md">
        <h3 class="font-bold text-lg mb-4">Create Fantasy League</h3>

        <form @submit.prevent="createLeague" class="space-y-4">

          <!-- Organization (locked to org 1 for now) -->
          <div class="form-control">
            <label class="label py-1">
              <span class="label-text text-sm">Organization</span>
              <span class="label-text-alt text-xs text-base-content/30">more orgs coming soon</span>
            </label>
            <select class="select select-bordered select-sm opacity-60" disabled>
              <option selected>SIAHL at San Jose</option>
            </select>
          </div>

          <!-- HB League selector -->
          <div class="form-control">
            <label class="label py-1"><span class="label-text text-sm">League</span></label>
            <select v-model.number="createForm.hb_league_id" class="select select-bordered select-sm" required @change="onLeagueChange">
              <option :value="null" disabled>Select a league…</option>
              <option v-for="lg in hbLeagues" :key="lg.id" :value="lg.id">{{ lg.league_name }}</option>
            </select>
            <div v-if="hbLeaguesLoading" class="text-xs text-base-content/40 mt-1">Loading leagues…</div>
          </div>

          <!-- Level selector -->
          <div class="form-control">
            <label class="label py-1"><span class="label-text text-sm">Level</span></label>
            <select v-model.number="createForm.level_id" class="select select-bordered select-sm" required :disabled="!createForm.hb_league_id || levelsLoading" @change="onLevelChange">
              <option :value="null" disabled>{{ createForm.hb_league_id ? (levelsLoading ? 'Loading…' : 'Select a level…') : 'Select a league first…' }}</option>
              <option v-for="lvl in levels" :key="lvl.level_id" :value="lvl.level_id">
                {{ lvl.short_name || lvl.level_name }}
              </option>
            </select>
          </div>

          <!-- Max managers (shown after level selected, capped by pool) -->
          <div v-if="createForm.level_id" class="form-control">
            <label class="label py-1">
              <span class="label-text text-sm">Max Managers</span>
              <span v-if="poolLoading" class="label-text-alt text-xs text-base-content/40">calculating…</span>
              <span v-else-if="poolMaxManagers" class="label-text-alt text-xs text-base-content/40">up to {{ poolMaxManagers }} based on player pool</span>
            </label>
            <select v-model.number="createForm.max_managers" class="select select-bordered select-sm" :disabled="poolLoading">
              <option v-for="n in managerOptions" :key="n" :value="n">{{ n }}</option>
            </select>
          </div>

          <!-- Team name -->
          <div class="form-control">
            <label class="label py-1"><span class="label-text text-sm">Your Team Name</span></label>
            <input v-model="createForm.team_name" type="text" placeholder="e.g. Ice Bandits" class="input input-bordered input-sm" required />
          </div>

          <!-- Season label -->
          <div class="form-control">
            <label class="label py-1"><span class="label-text text-sm">Season Label</span></label>
            <input v-model="createForm.season_label" type="text" placeholder="e.g. Spring 2026" class="input input-bordered input-sm" required />
          </div>

          <!-- Draft dates row 1, Season Starts row 2 -->
          <div class="grid grid-cols-2 gap-3">
            <div class="form-control">
              <label class="label py-1"><span class="label-text text-xs">Draft Opens</span></label>
              <input v-model="createForm.draft_opens_at" type="datetime-local" class="input input-bordered w-full h-auto min-h-[3.5rem] py-2 text-sm" />
            </div>
            <div class="form-control">
              <label class="label py-1"><span class="label-text text-xs">Draft Closes *</span></label>
              <input v-model="createForm.draft_closes_at" type="datetime-local" class="input input-bordered w-full h-auto min-h-[3.5rem] py-2 text-sm" required />
            </div>
          </div>
          <div class="text-xs text-base-content/40 -mt-2 mb-1">All picks must be made between Draft Opens and Draft Closes. If you miss your turn, a pick is automatically made for you — the highest Fantasy Points player still available.</div>
          <div class="form-control">
            <label class="label py-1"><span class="label-text text-xs">Season Starts</span></label>
            <input v-model="createForm.season_starts_at" type="datetime-local" class="input input-bordered w-full h-auto min-h-[3.5rem] py-2 text-sm" required :min="nowLocal" />
          </div>

          <!-- Private toggle -->
          <div class="form-control">
            <label class="label cursor-pointer justify-start gap-3">
              <input type="checkbox" v-model="createForm.is_private" class="toggle toggle-sm" />
              <span class="label-text text-sm">🔒 Private league (invite only)</span>
            </label>
          </div>

          <div v-if="createError" class="alert alert-error text-sm py-2">{{ createError }}</div>

          <div class="modal-action mt-2">
            <button type="button" class="btn btn-ghost btn-sm" @click="showCreateModal = false">Cancel</button>
            <button v-if="isAuthenticated" type="submit" class="btn btn-primary btn-sm" :disabled="creating">
              <span v-if="creating" class="loading loading-spinner loading-xs"></span>
              Create
            </button>
            <button v-else type="button" class="btn btn-warning btn-sm" @click="loginWithRedirect()">
              Login to Create
            </button>
          </div>
        </form>
      </div>
      <div class="modal-backdrop"></div>
    </div>

    <!-- Join Code reveal modal (shown after creating a private league) -->
    <div v-if="showJoinCodeModal" class="modal modal-open">
      <div class="modal-box max-w-sm text-center">
        <div class="text-4xl mb-3">🔒</div>
        <h3 class="font-bold text-lg mb-2">Private League Created!</h3>
        <p class="text-sm text-base-content/60 mb-4">Share this code with friends so they can join:</p>
        <div class="bg-base-300 rounded-lg px-6 py-4 text-3xl font-mono font-bold tracking-widest text-primary">
          {{ createdJoinCode }}
        </div>
        <p class="text-xs text-base-content/40 mt-3">You can find this code again in the league settings.</p>
        <div class="modal-action justify-center">
          <button class="btn btn-primary btn-sm" @click="showJoinCodeModal = false">Got it!</button>
        </div>
      </div>
      <div class="modal-backdrop" @click="showJoinCodeModal = false"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApiClient } from '@/api/client'
import { useAuth0 } from '@auth0/auth0-vue'

const router = useRouter()
const api = useApiClient()
const { isAuthenticated, loginWithRedirect } = useAuth0()
const nowLocal = computed(() => {
  const d = new Date(); const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
})

const leagues = ref([])
const loading = ref(true)

// Create modal state
const showCreateModal = ref(false)
const createModalKey = ref(0)
const creating = ref(false)
const createError = ref('')
const createForm = ref({
  hb_league_id: null,
  level_id: null,
  team_name: '',
  is_private: true,
  season_label: '',
  season_starts_at: '2026-04-01T00:00',
  draft_opens_at: '2026-03-28T16:00',
  draft_closes_at: '2026-03-30T23:00',
  max_managers: null,
})
const createdJoinCode = ref('')
const showJoinCodeModal = ref(false)
const showJoinCodeEntry = ref(false)
const joinCodeEntry = ref('')
const joinCodeError = ref('')

// League + level selectors
const hbLeagues = ref([])
const hbLeaguesLoading = ref(false)
const levels = ref([])
const levelsLoading = ref(false)

// Pool info (max managers cap)
const poolMaxManagers = ref(null)
const poolLoading = ref(false)

const managerOptions = computed(() => {
  const max = poolMaxManagers.value || 12
  const opts = []
  for (let i = 2; i <= max; i++) opts.push(i)
  return opts
})

// Private join modal
const showPrivateJoinModal = ref(false)
const privateJoinLeague = ref(null)
const privateJoinCode = ref('')
const privateJoinError = ref('')

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
    active: 'badge-neutral',
    completed: 'badge-neutral',
  }[s] || 'badge-ghost'
}

const groupedLeagues = computed(() => {
  const groups = {}
  for (const league of leagues.value) {
    const label = STATUS_LABELS[league.status] || league.status
    if (!groups[label]) groups[label] = []
    groups[label].push(league)
  }
  return Object.entries(groups).map(([label, ls]) => ({
    label,
    leagues: ls.slice().sort((a, b) => (b.is_member ? 1 : 0) - (a.is_member ? 1 : 0) || (a.name || '').localeCompare(b.name || ''))
  }))
    .sort((a, b) => {
      const ai = STATUS_ORDER.indexOf(leagues.value.find(l => STATUS_LABELS[l.status] === a.label)?.status || '')
      const bi = STATUS_ORDER.indexOf(leagues.value.find(l => STATUS_LABELS[l.status] === b.label)?.status || '')
      return ai - bi
    })
})

async function loadLeagues() {
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

async function loadHbLeagues() {
  hbLeaguesLoading.value = true
  try {
    const { data } = await api.get('/api/fantasy/hb-leagues', { params: { org_id: 1 } })
    hbLeagues.value = data.leagues || []
  } catch {
    hbLeagues.value = []
  } finally {
    hbLeaguesLoading.value = false
  }
}

async function loadLevels(leagueId) {
  levels.value = []
  if (!leagueId) return
  levelsLoading.value = true
  try {
    const { data } = await api.get('/api/fantasy/active-levels', { params: { org_id: 1, league_id: leagueId } })
    levels.value = data.levels || []
  } catch {
    levels.value = []
  } finally {
    levelsLoading.value = false
  }
}

async function loadPoolInfo(levelId, hbLeagueId) {
  poolMaxManagers.value = null
  createForm.value.max_managers = null
  if (!levelId) return
  poolLoading.value = true
  try {
    const { data } = await api.get('/api/fantasy/level-pool', {
      params: { level_id: levelId, hb_league_id: hbLeagueId, org_id: 1 }
    })
    poolMaxManagers.value = data.max_managers || 12
    // Default to max
    createForm.value.max_managers = poolMaxManagers.value
  } catch {
    poolMaxManagers.value = 12
    createForm.value.max_managers = 12
  } finally {
    poolLoading.value = false
  }
}

async function openCreateModal() {
  createModalKey.value++
  showCreateModal.value = true
  createError.value = ''
  poolMaxManagers.value = null
  createForm.value = {
    hb_league_id: null,
    level_id: null,
    team_name: '',
    is_private: true,
    season_label: '',
    season_starts_at: '',
    draft_opens_at: '',
    draft_closes_at: '',
    max_managers: null,
  }
  levels.value = []
  if (!hbLeagues.value.length) {
    await loadHbLeagues()
  }
}

function onLeagueChange() {
  createForm.value.level_id = null
  createForm.value.max_managers = null
  poolMaxManagers.value = null
  loadLevels(createForm.value.hb_league_id)
}

function onLevelChange() {
  loadPoolInfo(createForm.value.level_id, createForm.value.hb_league_id)
}

async function createLeague() {
  createError.value = ''
  creating.value = true
  try {
    const lvl = levels.value.find(l => l.level_id === createForm.value.level_id)
    const levelLabel = lvl ? (lvl.short_name || lvl.level_name) : 'Level ?'
    const seasonLabel = createForm.value.season_label || undefined
    const leagueName = seasonLabel ? `${levelLabel} — ${seasonLabel}` : levelLabel

    const { data } = await api.post('/api/fantasy/leagues', {
      name: leagueName,
      team_name: createForm.value.team_name,
      level_id: createForm.value.level_id,
      hb_league_id: createForm.value.hb_league_id,
      season_label: seasonLabel,
      is_private: createForm.value.is_private,
      max_managers_override: createForm.value.max_managers,
      season_starts_at: createForm.value.season_starts_at ? new Date(createForm.value.season_starts_at).toISOString() : undefined,
      draft_opens_at: createForm.value.draft_opens_at ? new Date(createForm.value.draft_opens_at).toISOString() : undefined,
      draft_closes_at: new Date(createForm.value.draft_closes_at).toISOString(),
    })
    showCreateModal.value = false
    if (data.is_private && data.join_code) {
      createdJoinCode.value = data.join_code
      showJoinCodeModal.value = true
      setTimeout(() => router.push(`/fantasy/${data.id}`), 0)
    } else {
      router.push(`/fantasy/${data.id}`)
    }
    createForm.value = {
      hb_league_id: null, level_id: null, team_name: '', is_private: true,
      season_label: '', season_starts_at: '2026-04-01T00:00', draft_opens_at: '2026-03-28T16:00', draft_closes_at: '2026-03-30T23:00', max_managers: null,
    }
  } catch (e) {
    createError.value = e?.response?.data?.message || 'Failed to create league'
  } finally {
    creating.value = false
  }
}

async function submitJoinCode() {
  joinCodeError.value = ''
  const code = joinCodeEntry.value.trim().toUpperCase()
  if (code.length < 6) return
  if (!isAuthenticated.value) {
    loginWithRedirect()
    return
  }
  try {
    const { data } = await api.get(`/api/fantasy/league-by-code/${code}`)
    showJoinCodeEntry.value = false
    joinCodeEntry.value = ''
    router.push(`/fantasy/${data.id}?join_code=${code}`)
  } catch (e) {
    joinCodeError.value = e?.response?.data?.message || 'Code not found. Check with your league creator.'
  }
}

function startJoinPrivate(league) {
  privateJoinLeague.value = league
  privateJoinCode.value = ''
  privateJoinError.value = ''
  showPrivateJoinModal.value = true
}

function goToPrivateLeague() {
  if (privateJoinLeague.value) {
    router.push(`/fantasy/${privateJoinLeague.value.id}?join_code=${privateJoinCode.value.toUpperCase()}`)
    showPrivateJoinModal.value = false
  }
}

onMounted(() => {
  loadLeagues()
})
</script>
