<template>
  <div class="max-w-5xl mx-auto px-4 py-6">
    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-12">
      <span class="loading loading-spinner loading-lg text-primary"></span>
    </div>

    <template v-else-if="league">
      <!-- Header -->
      <div class="mb-6">
        <div class="flex items-start justify-between flex-wrap gap-3">
          <div>
            <div class="text-xs text-base-content/40 mb-1">
              <RouterLink to="/fantasy" class="link link-hover">Fantasy</RouterLink> /
            </div>
            <h1 class="text-2xl font-extrabold tracking-tight">{{ league.name }}</h1>
            <p class="text-sm text-base-content/50 mt-1">
              Level: {{ league.level_name }}
              <span v-if="league.season_label"> · {{ league.season_label }}</span>
            </p>
          </div>
          <div class="flex items-center gap-2 flex-wrap">
            <span class="badge" :class="statusBadgeClass(league.status)">
              {{ statusLabel(league.status) }}
            </span>
            <!-- Join button -->
            <button
              v-if="!league.is_member && league.status === 'forming'"
              class="btn btn-primary btn-sm"
              @click="showJoinModal = true"
            >
              Join League
            </button>
            <!-- Open draft -->
            <button
              v-if="league.is_creator && league.status === 'forming' && (league.manager_count || 0) >= 2"
              class="btn btn-warning btn-sm"
              :disabled="openingDraft"
              @click="openDraft"
            >
              <span v-if="openingDraft" class="loading loading-spinner loading-xs"></span>
              Open Draft
            </button>
            <!-- Start season -->
            <button
              v-if="league.is_creator && ['drafting', 'draft_open'].includes(league.status)"
              class="btn btn-success btn-sm"
              :disabled="startingSeason"
              @click="startSeason"
            >
              <span v-if="startingSeason" class="loading loading-spinner loading-xs"></span>
              Start Season
            </button>
          </div>
        </div>

        <!-- Stats row -->
        <div class="flex gap-6 mt-3 text-sm text-base-content/60">
          <span>👥 {{ league.manager_count }} / {{ league.max_managers }} managers</span>
          <span>📋 {{ league.roster_skaters }} skaters + {{ league.roster_goalies }} goalie(s) per team</span>
          <span>⏱ {{ league.draft_pick_hours }}h per pick</span>
        </div>
      </div>

      <!-- Tabs -->
      <div class="tabs tabs-boxed mb-6 w-fit">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="tab"
          :class="{ 'tab-active': activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- ── Draft Tab ── -->
      <div v-if="activeTab === 'draft'">
        <div v-if="['forming'].includes(league.status)" class="text-center py-10 text-base-content/40">
          <div class="text-4xl mb-2">⏳</div>
          <p>Waiting for the league creator to open the draft.</p>
          <p v-if="!league.is_member" class="mt-2">
            <button class="btn btn-primary btn-sm" @click="showJoinModal = true">Join to participate</button>
          </p>
        </div>

        <div v-else>
          <!-- Current pick info -->
          <div v-if="currentPick" class="alert mb-4" :class="currentPick.user_id === myUserId ? 'alert-success' : 'alert-info'">
            <div>
              <p class="font-semibold">
                <template v-if="currentPick.user_id === myUserId">
                  ⬆️ It's your pick! Round {{ currentPick.round }}, Pick {{ currentPick.overall_pick }}
                </template>
                <template v-else>
                  🕐 Waiting on {{ currentPick.manager?.team_name || 'a manager' }} — Pick #{{ currentPick.overall_pick }}
                </template>
              </p>
              <p v-if="currentPick.deadline" class="text-sm opacity-70 mt-0.5">
                Deadline: {{ formatDeadline(currentPick.deadline) }}
              </p>
            </div>
          </div>
          <div v-else-if="['active', 'completed'].includes(league.status)" class="alert alert-success mb-4">
            <span>✅ Draft complete! Season is {{ league.status === 'active' ? 'active' : 'completed' }}.</span>
          </div>

          <!-- Player picker (only when it's your turn) -->
          <div v-if="currentPick && currentPick.user_id === myUserId && league.is_member" class="mb-6">
            <div class="card bg-base-200 shadow">
              <div class="card-body p-4">
                <h3 class="font-semibold mb-3">Pick a Player</h3>

                <!-- Filter -->
                <div class="flex gap-3 mb-3 flex-wrap">
                  <input
                    v-model="playerFilter"
                    type="text"
                    placeholder="Search player..."
                    class="input input-bordered input-sm flex-1 min-w-[160px]"
                  />
                  <select v-model="positionFilter" class="select select-bordered select-sm w-32">
                    <option value="">All</option>
                    <option value="skater">Skaters</option>
                    <option value="goalie">Goalies</option>
                  </select>
                </div>

                <div class="overflow-x-auto max-h-72 overflow-y-auto">
                  <table class="table table-xs w-full">
                    <thead class="sticky top-0 bg-base-200">
                      <tr>
                        <th>Player</th>
                        <th>Pos</th>
                        <th>GP</th>
                        <th>G</th>
                        <th>A</th>
                        <th>PPG</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="p in filteredPool" :key="p.hb_human_id" class="hover">
                        <td>{{ p.first_name }} {{ p.last_name }}</td>
                        <td>{{ p.is_goalie ? 'G' : 'SK' }}</td>
                        <td>{{ p.games_played }}</td>
                        <td>{{ p.goals }}</td>
                        <td>{{ p.assists }}</td>
                        <td>{{ p.ppg }}</td>
                        <td>
                          <button
                            class="btn btn-xs btn-primary"
                            :disabled="picking"
                            @click="pickPlayer(p)"
                          >
                            Pick
                          </button>
                        </td>
                      </tr>
                      <tr v-if="filteredPool.length === 0">
                        <td colspan="7" class="text-center text-base-content/40 py-4">No available players</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-if="pickError" class="text-error text-xs mt-2">{{ pickError }}</div>
              </div>
            </div>
          </div>

          <!-- Draft board -->
          <div class="overflow-x-auto">
            <table class="table table-xs w-full">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Round</th>
                  <th>Manager</th>
                  <th>Player</th>
                  <th>Deadline</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="pick in draftQueue"
                  :key="pick.overall_pick"
                  :class="{
                    'bg-success/10': pick.picked_at,
                    'bg-warning/10': !pick.picked_at && !pick.is_skipped && pick === currentPick,
                    'opacity-40': pick.is_skipped,
                  }"
                >
                  <td>{{ pick.overall_pick }}</td>
                  <td>{{ pick.round }}</td>
                  <td>{{ pick.manager?.team_name || '—' }}</td>
                  <td>{{ pick.player_name || (pick.picked_at ? '?' : '—') }}</td>
                  <td class="text-xs">{{ pick.deadline ? formatDeadline(pick.deadline) : '—' }}</td>
                  <td>
                    <span v-if="pick.is_skipped" class="badge badge-xs badge-error">Skipped</span>
                    <span v-else-if="pick.picked_at" class="badge badge-xs badge-success">Done</span>
                    <span v-else-if="pick === currentPick" class="badge badge-xs badge-warning">On clock</span>
                    <span v-else class="badge badge-xs badge-ghost">Pending</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- ── Rosters Tab ── -->
      <div v-if="activeTab === 'rosters'">
        <div v-if="!league.managers?.length" class="text-center py-10 text-base-content/40">No managers yet.</div>
        <div v-else class="space-y-4">
          <div
            v-for="mgr in league.managers"
            :key="mgr.user_id"
            class="card bg-base-200 shadow-sm"
          >
            <div class="card-body p-4">
              <h3 class="font-semibold">{{ mgr.team_name }}</h3>
              <p class="text-xs text-base-content/40 mb-2">{{ mgr.display_name }}</p>
              <RosterList :league-id="league.id" :user-id="mgr.user_id" />
            </div>
          </div>
        </div>
      </div>

      <!-- ── Standings Tab ── -->
      <div v-if="activeTab === 'standings'">
        <div v-if="standingsLoading" class="flex justify-center py-8">
          <span class="loading loading-spinner text-primary"></span>
        </div>
        <div v-else-if="!standings.length" class="text-center py-10 text-base-content/40">
          No standings yet. Season starts after the draft.
        </div>
        <div v-else class="overflow-x-auto">
          <table class="table w-full">
            <thead>
              <tr>
                <th>#</th>
                <th>Team</th>
                <th>Manager</th>
                <th class="text-right">Total Pts</th>
                <th class="text-right">Week Pts</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in standings"
                :key="row.user_id"
                :class="{ 'bg-primary/10 font-semibold': row.user_id === myUserId }"
              >
                <td>{{ row.rank || '—' }}</td>
                <td>{{ row.team_name }}</td>
                <td class="text-base-content/60 text-sm">{{ row.display_name }}</td>
                <td class="text-right">{{ row.total_points }}</td>
                <td class="text-right">{{ row.week_points }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ── My Team Tab ── -->
      <div v-if="activeTab === 'myteam'">
        <div v-if="!league.is_member" class="text-center py-10 text-base-content/40">
          <p>You're not in this league.</p>
          <button v-if="league.status === 'forming'" class="btn btn-primary btn-sm mt-3" @click="showJoinModal = true">
            Join League
          </button>
        </div>
        <div v-else>
          <h3 class="font-semibold mb-3">Your Roster</h3>
          <RosterList :league-id="league.id" :user-id="myUserId" show-points />
        </div>
      </div>
    </template>

    <div v-else class="text-center py-16 text-base-content/40">
      League not found.
    </div>

    <!-- Join Modal -->
    <div v-if="showJoinModal" class="modal modal-open">
      <div class="modal-box max-w-sm">
        <h3 class="font-bold text-lg mb-4">Join League</h3>
        <form @submit.prevent="joinLeague" class="space-y-4">
          <div class="form-control">
            <label class="label"><span class="label-text text-sm">Your Team Name</span></label>
            <input
              v-model="joinForm.team_name"
              type="text"
              placeholder="e.g. Ice Bandits"
              class="input input-bordered input-sm"
              required
            />
          </div>
          <div v-if="joinError" class="alert alert-error text-sm py-2">{{ joinError }}</div>
          <div class="modal-action">
            <button type="button" class="btn btn-ghost btn-sm" @click="showJoinModal = false">Cancel</button>
            <button type="submit" class="btn btn-primary btn-sm" :disabled="joining">
              <span v-if="joining" class="loading loading-spinner loading-xs"></span>
              Join
            </button>
          </div>
        </form>
      </div>
      <div class="modal-backdrop" @click="showJoinModal = false"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuth0 } from '@auth0/auth0-vue'
import { useUserStore } from '@/stores/user'
import { useApiClient } from '@/api/client'

// ── Inline mini-component for roster list ─────────────────────────────────
const RosterList = {
  name: 'RosterList',
  props: {
    leagueId: { type: Number, required: true },
    userId: { type: Number, required: true },
    showPoints: { type: Boolean, default: false },
  },
  template: `
    <div>
      <div v-if="rLoading" class="text-xs text-base-content/40">Loading…</div>
      <div v-else-if="!roster.length" class="text-xs text-base-content/40 italic">No players drafted yet.</div>
      <div v-else class="flex flex-wrap gap-2">
        <span
          v-for="p in roster"
          :key="p.hb_human_id"
          class="badge badge-outline gap-1 text-xs"
          :class="p.is_goalie ? 'badge-secondary' : 'badge-primary'"
        >
          {{ p.is_goalie ? '🥅' : '🏒' }} {{ p.player_name }}
          <span v-if="p.round_picked" class="opacity-50 text-xs">R{{ p.round_picked }}</span>
        </span>
      </div>
    </div>
  `,
  setup(props) {
    const api = useApiClient()
    const roster = ref([])
    const rLoading = ref(true)

    async function load() {
      rLoading.value = true
      try {
        const { data } = await api.get(`/api/fantasy/leagues/${props.leagueId}/roster/${props.userId}`)
        roster.value = data.roster || []
      } catch {
        roster.value = []
      } finally {
        rLoading.value = false
      }
    }

    onMounted(load)
    return { roster, rLoading }
  },
}

// ── Main component ────────────────────────────────────────────────────────
const route = useRoute()
const api = useApiClient()
const { isAuthenticated } = useAuth0()
const userStore = useUserStore()

const league = ref(null)
const loading = ref(true)
const draftQueue = ref([])
const pool = ref({ skaters: [], goalies: [] })
const standings = ref([])
const standingsLoading = ref(false)

const activeTab = ref('draft')
const tabs = [
  { id: 'draft', label: '📋 Draft' },
  { id: 'rosters', label: '👥 Rosters' },
  { id: 'standings', label: '🏆 Standings' },
  { id: 'myteam', label: '⭐ My Team' },
]

const showJoinModal = ref(false)
const joining = ref(false)
const joinError = ref('')
const joinForm = ref({ team_name: '' })

const openingDraft = ref(false)
const startingSeason = ref(false)

const playerFilter = ref('')
const positionFilter = ref('')
const picking = ref(false)
const pickError = ref('')

const myUserId = computed(() => userStore.predUser?.id)

const currentPick = computed(() =>
  draftQueue.value.find(p => !p.picked_at && !p.is_skipped)
)

const filteredPool = computed(() => {
  const allPlayers = [
    ...(positionFilter.value === 'goalie' ? [] : pool.value.skaters),
    ...(positionFilter.value === 'skater' ? [] : pool.value.goalies),
  ]
  if (!playerFilter.value) return allPlayers
  const q = playerFilter.value.toLowerCase()
  return allPlayers.filter(p =>
    `${p.first_name} ${p.last_name}`.toLowerCase().includes(q)
  )
})

function statusLabel(s) {
  return { forming: 'Forming', draft_open: 'Draft Open', drafting: 'Drafting', active: 'Active', completed: 'Completed' }[s] || s
}

function statusBadgeClass(s) {
  return { forming: 'badge-info', draft_open: 'badge-warning', drafting: 'badge-warning', active: 'badge-success', completed: 'badge-neutral' }[s] || 'badge-ghost'
}

function formatDeadline(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function loadLeague() {
  loading.value = true
  try {
    const { data } = await api.get(`/api/fantasy/leagues/${route.params.id}`)
    league.value = data
  } catch {
    league.value = null
  } finally {
    loading.value = false
  }
}

async function loadDraftQueue() {
  try {
    const { data } = await api.get(`/api/fantasy/leagues/${route.params.id}/draft/queue`)
    draftQueue.value = data.queue || []
  } catch {
    draftQueue.value = []
  }
}

async function loadPool() {
  try {
    const { data } = await api.get(`/api/fantasy/leagues/${route.params.id}/pool`)
    pool.value = data
  } catch {
    pool.value = { skaters: [], goalies: [] }
  }
}

async function loadStandings() {
  standingsLoading.value = true
  try {
    const { data } = await api.get(`/api/fantasy/leagues/${route.params.id}/standings`)
    standings.value = data.standings || []
  } catch {
    standings.value = []
  } finally {
    standingsLoading.value = false
  }
}

async function joinLeague() {
  joinError.value = ''
  joining.value = true
  try {
    await api.post(`/api/fantasy/leagues/${route.params.id}/join`, { team_name: joinForm.value.team_name })
    showJoinModal.value = false
    joinForm.value = { team_name: '' }
    await loadLeague()
  } catch (e) {
    joinError.value = e?.response?.data?.message || 'Failed to join'
  } finally {
    joining.value = false
  }
}

async function openDraft() {
  openingDraft.value = true
  try {
    await api.post(`/api/fantasy/leagues/${route.params.id}/open-draft`)
    await loadLeague()
    await loadDraftQueue()
    await loadPool()
  } catch (e) {
    alert(e?.response?.data?.message || 'Failed to open draft')
  } finally {
    openingDraft.value = false
  }
}

async function startSeason() {
  startingSeason.value = true
  try {
    await api.post(`/api/fantasy/leagues/${route.params.id}/start`)
    await loadLeague()
  } catch (e) {
    alert(e?.response?.data?.message || 'Failed to start season')
  } finally {
    startingSeason.value = false
  }
}

async function pickPlayer(player) {
  pickError.value = ''
  picking.value = true
  try {
    await api.post(`/api/fantasy/leagues/${route.params.id}/draft`, { hb_human_id: player.hb_human_id })
    await loadDraftQueue()
    await loadPool()
    await loadLeague()
  } catch (e) {
    pickError.value = e?.response?.data?.message || 'Failed to pick player'
  } finally {
    picking.value = false
  }
}

// Load standings when tab changes
watch(activeTab, (tab) => {
  if (tab === 'standings') loadStandings()
})

onMounted(async () => {
  await loadLeague()
  if (league.value && !['forming'].includes(league.value.status)) {
    await Promise.all([loadDraftQueue(), loadPool()])
  }
})
</script>
