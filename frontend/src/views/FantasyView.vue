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

          <!-- Season used for player pool (shown after level selected) -->
          <div v-if="createForm.level_id && poolSeasonName" class="form-control">
            <label class="label py-1">
              <span class="label-text text-sm text-base-content/50">Player pool from</span>
            </label>
            <div class="flex items-center gap-2 px-1">
              <span class="text-sm font-semibold">📅 {{ poolSeasonName }}</span>
              <span class="text-xs text-base-content/40">(most recent season with games)</span>
            </div>
          </div>

          <!-- Minimum games played filter (shown after level selected) -->
          <div v-if="createForm.level_id" class="form-control">
            <label class="label py-1">
              <span class="label-text text-sm">Minimum games played</span>
              <span class="label-text-alt text-xs text-base-content/40">filters the player pool</span>
            </label>
            <select v-model.number="createForm.min_games_played" class="select select-bordered select-sm" @change="onMinGamesChange">
              <option v-for="n in [1,2,3,4,5]" :key="n" :value="n">{{ n }}</option>
            </select>
          </div>

          <!-- Available player counts (shown after level selected) -->
          <div v-if="createForm.level_id && !poolLoading" class="form-control">
            <label class="label py-1">
              <span class="label-text text-sm text-base-content/50">Available players</span>
            </label>
            <div class="flex flex-wrap items-center gap-3 px-1">
              <span class="text-sm"><span class="font-semibold text-primary">{{ poolPlayerCounts.skaters }}</span> skaters</span>
              <span class="text-sm"><span class="font-semibold text-primary">{{ poolPlayerCounts.goalies }}</span> goalies</span>
              <span class="text-sm"><span class="font-semibold text-primary">{{ poolPlayerCounts.refs }}</span> refs</span>
            </div>
          </div>

          <!-- Auto-adjust rosters toggle (shown after level selected) -->
          <div v-if="createForm.level_id && !poolLoading" class="form-control">
            <label class="label cursor-pointer justify-start gap-3">
              <input type="checkbox" v-model="createForm.auto_adjust_rosters" class="toggle toggle-sm" />
              <span class="label-text text-sm">⚖️ Auto adjust rosters based on number of managers</span>
            </label>
            <div v-if="createForm.auto_adjust_rosters" class="text-xs text-base-content/40 px-1 mt-1">
              Roster sizes are computed when the draft opens, based on how many managers actually joined.
              (e.g. 6 managers → ~10 skaters / 1 goalie / 1 ref each; 10 managers → ~6 / 0 / 0).
            </div>
          </div>

          <!-- Roster size per manager (shown after level selected) -->
          <div v-if="createForm.level_id && !poolLoading && !createForm.auto_adjust_rosters" class="form-control">
            <label class="label py-1">
              <span class="label-text text-sm">Roster size per manager</span>
            </label>
            <div class="grid grid-cols-3 gap-2">
              <div class="form-control">
                <label class="label py-0.5 justify-center">
                  <span class="label-text text-xs text-base-content/50">Skaters</span>
                </label>
                <select v-model.number="createForm.roster_skaters" class="select select-bordered select-sm">
                  <option v-for="n in [1,2,3,4,5,6,7,8,9,10]" :key="n" :value="n">{{ n }}</option>
                </select>
              </div>
              <div class="form-control">
                <label class="label py-0.5 justify-center">
                  <span class="label-text text-xs text-base-content/50">Goalies</span>
                </label>
                <select v-model.number="createForm.roster_goalies" class="select select-bordered select-sm">
                  <option v-for="n in [0,1,2,3,4,5]" :key="n" :value="n">{{ n }}</option>
                </select>
              </div>
              <div class="form-control">
                <label class="label py-0.5 justify-center">
                  <span class="label-text text-xs text-base-content/50">Refs</span>
                </label>
                <select v-model.number="createForm.roster_refs" class="select select-bordered select-sm">
                  <option v-for="n in [0,1,2,3,4,5]" :key="n" :value="n">{{ n }}</option>
                </select>
              </div>
            </div>
          </div>

          <!-- Max managers (shown after roster sizes selected) -->
          <div v-if="createForm.level_id && !poolLoading" class="form-control">
            <label class="label py-1">
              <span class="label-text text-sm">Max Managers</span>
              <span class="label-text-alt text-xs" :class="managerOptions.length > 0 ? 'text-base-content/40' : 'text-error'">
                {{ managerOptions.length > 0 ? `up to ${managerOptions[managerOptions.length-1]}` : 'insufficient players' }}
              </span>
            </label>
            <select v-model.number="createForm.max_managers" class="select select-bordered select-sm" :disabled="poolLoading || managerOptions.length === 0">
              <option v-for="n in managerOptions" :key="n" :value="n">{{ n }}</option>
            </select>
          </div>

          <!-- Roster feasibility check (shown after max managers selected) -->
          <div v-if="createForm.level_id && createForm.max_managers && !poolLoading && !createForm.auto_adjust_rosters" class="form-control">
            <label class="label py-1">
              <span class="label-text text-sm text-base-content/50">Roster allocation</span>
              <span class="label-text-alt text-xs" :class="rosterFeasibility.skaters.ok && rosterFeasibility.goalies.ok && rosterFeasibility.refs.ok ? 'text-success' : 'text-error'">
                {{ rosterFeasibility.skaters.ok && rosterFeasibility.goalies.ok && rosterFeasibility.refs.ok ? '✓ feasible' : '✗ check numbers' }}
              </span>
            </label>
            <div class="flex flex-wrap items-center gap-3 px-1 text-sm">
              <span>Skaters: <span class="font-semibold" :class="rosterFeasibility.skaters.ok ? 'text-primary' : 'text-error'">{{ rosterFeasibility.skaters.needed }}</span> / {{ rosterFeasibility.skaters.available }}</span>
              <span>Goalies: <span class="font-semibold" :class="rosterFeasibility.goalies.ok ? 'text-primary' : 'text-error'">{{ rosterFeasibility.goalies.needed }}</span> / {{ rosterFeasibility.goalies.available }}</span>
              <span>Refs: <span class="font-semibold" :class="rosterFeasibility.refs.ok ? 'text-primary' : 'text-error'">{{ rosterFeasibility.refs.needed }}</span> / {{ rosterFeasibility.refs.available }}</span>
            </div>
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
import { ref, computed, onMounted, watch, nextTick } from 'vue'
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
  roster_skaters: 2,
  roster_goalies: 1,
  roster_refs: 1,
  auto_adjust_rosters: false,
  min_games_played: 1,
})
const createdJoinCode = ref('')
const showJoinCodeModal = ref(false)
const showJoinCodeEntry = ref(false)
const joinCodeEntry = ref('')

// Given a date (string or Date), find the first Friday at 7PM PT after that date
function firstFridayAfter(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')  // treat as local date
  // Advance past the date itself
  d.setDate(d.getDate() + 1)
  // Walk forward until Friday (day 5)
  while (d.getDay() !== 5) d.setDate(d.getDate() + 1)
  d.setHours(19, 0, 0, 0)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T19:00`
}

function addHours(dtStr, hours) {
  if (!dtStr) return ''
  const d = new Date(dtStr)
  d.setHours(d.getHours() + hours)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function addMins(dtStr, mins) {
  if (!dtStr) return ''
  const d = new Date(dtStr)
  d.setMinutes(d.getMinutes() + mins)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// Dates are auto-filled by loadPoolInfo based on last game date.
// Still cascade if user manually changes draft_opens_at so closes/season_start follow.
watch(() => createForm.value.draft_opens_at, (val, oldVal) => {
  // Only cascade if this is a manual change (not an auto-fill from level pick)
  if (val && val !== oldVal && !_autoFillingDates.value) {
    createForm.value.draft_closes_at = addHours(val, 48)
    createForm.value.season_starts_at = addHours(createForm.value.draft_closes_at, 6)
  }
})
const _autoFillingDates = ref(false)

// Watch roster sizes and reset max_managers if it exceeds new maximum
watch([() => createForm.value.roster_skaters, () => createForm.value.roster_goalies, () => createForm.value.roster_refs], () => {
  // Reset max_managers to null so user has to reselect
  createForm.value.max_managers = null
}, { flush: 'post' })

// When auto-adjust toggles, reset max_managers to the new cap so the dropdown defaults sensibly.
watch(() => createForm.value.auto_adjust_rosters, () => {
  const opts = managerOptions.value
  createForm.value.max_managers = opts.length ? opts[opts.length - 1] : null
}, { flush: 'post' })
const joinCodeError = ref('')

// League + level selectors
const hbLeagues = ref([])
const hbLeaguesLoading = ref(false)
const levels = ref([])
const levelsLoading = ref(false)

// Pool info (max managers cap + player counts)
const poolMaxManagers = ref(null)
const poolSeasonName = ref(null)
const poolLoading = ref(false)
const poolPlayerCounts = ref({ skaters: 0, goalies: 0, refs: 0 })

// Max managers based on roster selections - can't exceed available players
const managerOptions = computed(() => {
  const availableSkaters = poolPlayerCounts.value.skaters || 0

  // Auto-adjust mode: cap is floor(total_skaters / 2) so each manager gets at least 2 skaters.
  if (createForm.value.auto_adjust_rosters) {
    const max = Math.max(2, Math.floor(availableSkaters / 2))
    const opts = []
    for (let i = 2; i <= max; i++) opts.push(i)
    return opts
  }

  const skatersPerManager = createForm.value.roster_skaters || 2
  const goaliesPerManager = createForm.value.roster_goalies ?? 1
  const refsPerManager = createForm.value.roster_refs ?? 1

  const availableGoalies = poolPlayerCounts.value.goalies || 0
  const availableRefs = poolPlayerCounts.value.refs || 0

  // Max managers is limited by each position's availability
  const maxBySkaters = Math.floor(availableSkaters / skatersPerManager)
  const maxByGoalies = goaliesPerManager > 0 ? Math.floor(availableGoalies / goaliesPerManager) : 999
  const maxByRefs = refsPerManager > 0 ? Math.floor(availableRefs / refsPerManager) : 999

  const max = Math.max(2, Math.min(maxBySkaters, maxByGoalies, maxByRefs))
  const opts = []
  for (let i = 2; i <= max; i++) opts.push(i)
  return opts
})

// Feasibility check - shows if current selections are possible
const rosterFeasibility = computed(() => {
  const n = createForm.value.max_managers || 1
  const skatersNeeded = n * (createForm.value.roster_skaters || 2)
  const goaliesNeeded = n * (createForm.value.roster_goalies ?? 1)
  const refsNeeded = n * (createForm.value.roster_refs ?? 1)
  
  const availableSkaters = poolPlayerCounts.value.skaters || 0
  const availableGoalies = poolPlayerCounts.value.goalies || 0
  const availableRefs = poolPlayerCounts.value.refs || 0
  
  return {
    skaters: { needed: skatersNeeded, available: availableSkaters, ok: availableSkaters >= skatersNeeded },
    goalies: { needed: goaliesNeeded, available: availableGoalies, ok: availableGoalies >= goaliesNeeded || (createForm.value.roster_goalies ?? 1) === 0 },
    refs: { needed: refsNeeded, available: availableRefs, ok: availableRefs >= refsNeeded || (createForm.value.roster_refs ?? 1) === 0 },
  }
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

async function loadPoolInfo(levelId, hbLeagueId, { recomputeSkaters = true } = {}) {
  poolMaxManagers.value = null; poolSeasonName.value = null
  poolPlayerCounts.value = { skaters: 0, goalies: 0, refs: 0 }
  createForm.value.max_managers = null
  if (!levelId) return
  poolLoading.value = true
  try {
    const { data } = await api.get('/api/fantasy/level-pool', {
      params: {
        level_id: levelId,
        hb_league_id: hbLeagueId,
        org_id: 1,
        min_games: createForm.value.min_games_played || 1,
      }
    })
    poolMaxManagers.value = data.max_managers || 12
    poolSeasonName.value = data.resolved_season_name || null
    poolPlayerCounts.value = {
      skaters: data.skater_count || 0,
      goalies: data.goalie_count || 0,
      refs: data.ref_count || 0,
    }
    // Smart skaters default: limiting resource determines max managers.
    // With goalies=1/refs=1 defaults, max managers = min(goalies_available, refs_available).
    // Then skaters per team = floor(skaters_available / max_managers).
    // Note: 0 is valid for goalies/refs (no limit from that position).
    if (recomputeSkaters && !createForm.value.auto_adjust_rosters) {
      const gPer = createForm.value.roster_goalies ?? 1
      const rPer = createForm.value.roster_refs ?? 1
      const maxByG = gPer > 0 ? Math.floor(poolPlayerCounts.value.goalies / gPer) : 999
      const maxByR = rPer > 0 ? Math.floor(poolPlayerCounts.value.refs / rPer) : 999
      // limiting = max possible managers based on goalies/refs constraint
      const limiting = Math.max(1, Math.min(maxByG, maxByR))
      const skaterDefault = Math.max(1, Math.floor(poolPlayerCounts.value.skaters / limiting))
      createForm.value.roster_skaters = skaterDefault
    }
    // Default max_managers: highest valid option (respects auto-adjust cap when on).
    const opts = managerOptions.value
    createForm.value.max_managers = opts.length ? opts[opts.length - 1] : poolMaxManagers.value
    // Auto-fill draft dates based on last game in the season
    if (data.last_game_date) {
      const opens = firstFridayAfter(data.last_game_date)  // first Friday 7PM after last game
      const closes = addHours(opens, 48)                   // +48h
      const seasonStart = addHours(closes, 6)              // +6h after close
      _autoFillingDates.value = true
      createForm.value.draft_opens_at = opens
      createForm.value.draft_closes_at = closes
      createForm.value.season_starts_at = seasonStart
      await nextTick()
      _autoFillingDates.value = false
    }
  } catch {
    poolMaxManagers.value = 12
    createForm.value.max_managers = 12
  } finally {
    poolLoading.value = false
  }
}

function onMinGamesChange() {
  if (createForm.value.level_id) {
    loadPoolInfo(createForm.value.level_id, createForm.value.hb_league_id)
  }
}

async function openCreateModal() {
  createModalKey.value++
  showCreateModal.value = true
  createError.value = ''
  poolMaxManagers.value = null; poolSeasonName.value = null; poolPlayerCounts.value = { skaters: 0, goalies: 0, refs: 0 }
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
    roster_skaters: 2,
    roster_goalies: 1,
    roster_refs: 1,
    auto_adjust_rosters: false,
    min_games_played: 1,
  }
  levels.value = []
  if (!hbLeagues.value.length) {
    await loadHbLeagues()
  }
}

function onLeagueChange() {
  createForm.value.level_id = null
  createForm.value.max_managers = null
  poolMaxManagers.value = null; poolSeasonName.value = null; poolPlayerCounts.value = { skaters: 0, goalies: 0, refs: 0 }
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
      auto_adjust_rosters: createForm.value.auto_adjust_rosters,
      roster_skaters: createForm.value.roster_skaters,
      roster_goalies: createForm.value.roster_goalies,
      roster_refs: createForm.value.roster_refs,
      min_games_played: createForm.value.min_games_played,
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
      roster_skaters: 2, roster_goalies: 1, roster_refs: 1, auto_adjust_rosters: false, min_games_played: 1,
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
