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
            <div class="flex items-center gap-2">
              <h1 class="text-2xl font-extrabold tracking-tight">{{ league.name }}</h1>
              <span v-if="league.is_private" class="badge badge-neutral badge-sm">🔒 Private</span>
            </div>
            <p class="text-sm text-base-content/50 mt-1">
              Level: {{ league.level_name }}
              <span v-if="league.season_label"> · {{ league.season_label }}</span>
            </p>
            <p v-if="league.is_private && league.join_code && league.is_creator" class="text-xs text-base-content/40 mt-1">
              Invite code: <span class="font-mono font-bold text-base-content/70">{{ league.join_code }}</span>
            </p>
          </div>
          <div class="flex items-center gap-2 flex-wrap">
            <span class="badge" :class="statusBadgeClass(league.status)">
              {{ statusLabel(league.status) }}
            </span>
            <!-- Join button -->
            <button
              v-if="!league.is_member && ['forming', 'draft_open'].includes(league.status)"
              class="btn btn-primary btn-sm"
              @click="isAuthenticated ? showJoinModal = true : loginWithRedirect()"
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
          <span v-if="league.draft_closes_at && league.draft_opens_at">⏱ Draft: {{ formatDeadline(league.draft_opens_at) }} – {{ formatDeadline(league.draft_closes_at) }}</span>
          <span v-else>⏱ {{ league.draft_pick_hours }}h per pick</span>
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
        <div v-if="['forming', 'draft_open'].includes(league.status)" class="text-center py-10 text-base-content/40">
          <div class="text-4xl mb-2">⏳</div>
          <p>Waiting for the league creator to open the draft.</p>
          <p v-if="!league.is_member && ['forming', 'draft_open'].includes(league.status)" class="mt-2">
            <button class="btn btn-primary btn-sm" @click="isAuthenticated ? showJoinModal = true : loginWithRedirect()">Join to participate</button>
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
          <div v-else-if="['active', 'completed'].includes(league.status) && draftQueue.length > 0" class="alert alert-success mb-4">
            <span>✅ Draft complete! Season is {{ league.status === 'active' ? 'active' : 'completed' }}.</span>
          </div>

          <!-- Player pool panel (shown during draft, full pool with drafted indicators) -->
          <div v-if="['draft_open', 'drafting'].includes(league.status)" class="mb-6">
            <div class="card bg-base-200 shadow">
              <div class="card-body p-4">
                <div class="flex items-center justify-between mb-3 flex-wrap gap-2">
                  <h3 class="font-semibold">
                    Draft Pool
                    <span v-if="currentPick && currentPick.user_id === myUserId && league.is_member" class="badge badge-success badge-sm ml-2 animate-pulse">Your Pick!</span>
                  </h3>
                  <input
                    v-model="playerFilter"
                    type="text"
                    placeholder="Search player..."
                    class="input input-bordered input-xs w-40"
                  />
                </div>

                <!-- Skater / Goalie sub-tabs -->
                <div class="tabs tabs-boxed tabs-xs mb-3 w-fit">
                  <button class="tab" :class="{ 'tab-active': poolTab === 'skaters' }" @click="poolTab = 'skaters'"
                    :disabled="currentPick?.is_goalie_pick && currentPick?.user_id === myUserId">
                    Skaters
                  </button>
                  <button class="tab" :class="{ 'tab-active': poolTab === 'goalies' }" @click="poolTab = 'goalies'"
                    :disabled="currentPick && !currentPick?.is_goalie_pick && currentPick?.user_id === myUserId">
                    Goalies <span v-if="currentPick?.is_goalie_pick && currentPick?.user_id === myUserId" class="badge badge-xs badge-error ml-1">Round 1!</span>
                  </button>
                </div>

                <!-- Skaters table -->
                <div v-if="poolTab === 'skaters'" class="overflow-x-auto max-h-80 overflow-y-auto">
                  <table class="table table-xs w-full">
                    <thead class="sticky top-0 bg-base-200 z-10">
                      <tr>
                        <th class="cursor-pointer" @click="setSortKey('name')">Player <span v-if="sortKey === 'name'">{{ sortDir === 'asc' ? '▲' : '▼' }}</span></th>
                        <th class="cursor-pointer text-right" @click="setSortKey('games_played')">GP <span v-if="sortKey === 'games_played'">{{ sortDir === 'asc' ? '▲' : '▼' }}</span></th>
                        <th class="cursor-pointer text-right" @click="setSortKey('goals')">G <span v-if="sortKey === 'goals'">{{ sortDir === 'asc' ? '▲' : '▼' }}</span></th>
                        <th class="cursor-pointer text-right" @click="setSortKey('assists')">A <span v-if="sortKey === 'assists'">{{ sortDir === 'asc' ? '▲' : '▼' }}</span></th>
                        <th class="cursor-pointer text-right" @click="setSortKey('points')">Pts <span v-if="sortKey === 'points'">{{ sortDir === 'asc' ? '▲' : '▼' }}</span></th>
                        <th class="cursor-pointer text-right" @click="setSortKey('penalties')">Pen <span v-if="sortKey === 'penalties'">{{ sortDir === 'asc' ? '▲' : '▼' }}</span></th>
                        <th class="cursor-pointer text-right" @click="setSortKey('fantasy_points')">FP <span v-if="sortKey === 'fantasy_points'">{{ sortDir === 'asc' ? '▲' : '▼' }}</span></th>
                        <th class="cursor-pointer text-right" @click="setSortKey('fantasy_ppg')">FPPG <span v-if="sortKey === 'fantasy_ppg'">{{ sortDir === 'asc' ? '▲' : '▼' }}</span></th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="p in sortedSkaters"
                        :key="p.hb_human_id"
                        :class="p.drafted_by ? 'opacity-40' : 'hover'"
                      >
                        <td>{{ p.first_name }} {{ p.last_name }}</td>
                        <td class="text-right">{{ p.games_played }}</td>
                        <td class="text-right">{{ p.goals }}</td>
                        <td class="text-right">{{ p.assists }}</td>
                        <td class="text-right">{{ p.points }}</td>
                        <td class="text-right">{{ p.penalties }}</td>
                        <td class="text-right font-bold text-primary">{{ p.fantasy_points }}</td>
                        <td class="text-right text-base-content/60">{{ p.fantasy_ppg }}</td>
                        <td class="text-right">
                          <span v-if="p.drafted_by" class="text-xs text-base-content/40">{{ p.drafted_by.team_name }}</span>
                          <template v-else-if="currentPick && currentPick.user_id === myUserId && league.is_member">
                            <button
                              class="btn btn-xs btn-primary"
                              :disabled="picking"
                              @click="pickPlayer(p)"
                            >
                              Draft
                            </button>
                          </template>
                          <template v-else>
                            <button class="btn btn-xs btn-disabled" title="Not your turn" disabled>Draft</button>
                          </template>
                        </td>
                      </tr>
                      <tr v-if="sortedSkaters.length === 0">
                        <td colspan="9" class="text-center text-base-content/40 py-4">No skaters found</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <!-- Goalies table -->
                <div v-if="poolTab === 'goalies'" class="overflow-x-auto max-h-80 overflow-y-auto">
                  <table class="table table-xs w-full">
                    <thead class="sticky top-0 bg-base-200 z-10">
                      <tr>
                        <th>Player</th>
                        <th class="text-right">GP</th>
                        <th class="text-right">GAA</th>
                        <th class="text-right">SV%</th>
                        <th class="text-right">F.Pts</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="p in filteredGoalies"
                        :key="p.hb_human_id"
                        :class="p.drafted_by ? 'opacity-40' : 'hover'"
                      >
                        <td>{{ p.first_name }} {{ p.last_name }}</td>
                        <td class="text-right">{{ p.games_played }}</td>
                        <td class="text-right">{{ p.goals_against_avg ?? '—' }}</td>
                        <td class="text-right">{{ p.save_percentage != null ? (p.save_percentage * 100).toFixed(1) + '%' : '—' }}</td>
                        <td class="text-right font-bold text-primary">{{ p.fantasy_points }}</td>
                        <td class="text-right">
                          <span v-if="p.drafted_by" class="text-xs text-base-content/40">{{ p.drafted_by.team_name }}</span>
                          <template v-else-if="currentPick && currentPick.user_id === myUserId && league.is_member">
                            <button
                              class="btn btn-xs btn-primary"
                              :disabled="picking"
                              @click="pickPlayer(p)"
                            >
                              Draft
                            </button>
                          </template>
                          <template v-else>
                            <button class="btn btn-xs btn-disabled" title="Not your turn" disabled>Draft</button>
                          </template>
                        </td>
                      </tr>
                      <tr v-if="filteredGoalies.length === 0">
                        <td colspan="6" class="text-center text-base-content/40 py-4">No goalies found</td>
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
          <button v-if="['forming', 'draft_open'].includes(league.status)" class="btn btn-primary btn-sm mt-3" @click="isAuthenticated ? showJoinModal = true : loginWithRedirect()">
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
          <div v-if="league?.is_private" class="form-control">
            <label class="label"><span class="label-text text-sm">Invite Code</span></label>
            <input
              v-model="joinForm.join_code"
              type="text"
              placeholder="e.g. X7K2M9"
              class="input input-bordered input-sm uppercase"
              maxlength="6"
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
const { isAuthenticated, loginWithRedirect } = useAuth0()
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
const joinForm = ref({ team_name: '', join_code: '' })

const openingDraft = ref(false)
const startingSeason = ref(false)

const playerFilter = ref('')
const positionFilter = ref('')
const picking = ref(false)
const pickError = ref('')
const poolTab = ref('skaters')
const sortKey = ref('fantasy_points')
const sortDir = ref('desc')

function setSortKey(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'desc'
  }
}

const myUserId = computed(() => userStore.predUser?.id)

// My drafted players from the draft queue (already picked)
const myDraftedRoster = computed(() => {
  if (!myUserId.value) return []
  return draftQueue.value.filter(p => p.user_id === myUserId.value && p.picked_at && !p.is_skipped)
})

const myDraftedSkaters = computed(() =>
  myDraftedRoster.value.filter(p => {
    const player = [...(pool.value.skaters || []), ...(pool.value.goalies || [])]
      .find(pl => pl.hb_human_id === p.hb_human_id)
    return player && !player.is_goalie
  }).length
)

const myDraftedGoalies = computed(() =>
  myDraftedRoster.value.filter(p => {
    const player = [...(pool.value.skaters || []), ...(pool.value.goalies || [])]
      .find(pl => pl.hb_human_id === p.hb_human_id)
    return player && player.is_goalie
  }).length
)

// True when it's my turn AND I must pick a goalie (last pick(s) need to fill goalie slot)
const mustPickGoalie = computed(() => {
  if (!league.value || !currentPick.value || currentPick.value.user_id !== myUserId.value) return false
  const totalPicks = (league.value.roster_skaters || 0) + (league.value.roster_goalies || 0)
  const picksLeft = totalPicks - myDraftedRoster.value.length
  const goaliesNeeded = (league.value.roster_goalies || 1) - myDraftedGoalies.value
  return picksLeft <= goaliesNeeded
})

// True when it's my turn AND I must NOT pick a goalie (goalie slots full)
const mustPickSkater = computed(() => {
  if (!league.value || !currentPick.value || currentPick.value.user_id !== myUserId.value) return false
  return myDraftedGoalies.value >= (league.value.roster_goalies || 1)
})

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

const sortedSkaters = computed(() => {
  const skaters = pool.value.skaters || []
  const q = playerFilter.value.toLowerCase()
  const filtered = q
    ? skaters.filter(p => `${p.first_name} ${p.last_name}`.toLowerCase().includes(q))
    : skaters

  return [...filtered].sort((a, b) => {
    let aVal, bVal
    if (sortKey.value === 'name') {
      aVal = `${a.first_name} ${a.last_name}`
      bVal = `${b.first_name} ${b.last_name}`
      return sortDir.value === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal)
    }
    aVal = a[sortKey.value] ?? 0
    bVal = b[sortKey.value] ?? 0
    return sortDir.value === 'asc' ? aVal - bVal : bVal - aVal
  })
})

const filteredGoalies = computed(() => {
  const goalies = pool.value.goalies || []
  const q = playerFilter.value.toLowerCase()
  const filtered = q
    ? goalies.filter(p => `${p.first_name} ${p.last_name}`.toLowerCase().includes(q))
    : goalies
  return filtered
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
  return d.toLocaleString('en-US', { timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone, month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' })
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
    const payload = { team_name: joinForm.value.team_name }
    if (league.value?.is_private && joinForm.value.join_code) {
      payload.join_code = joinForm.value.join_code.toUpperCase()
    }
    await api.post(`/api/fantasy/leagues/${route.params.id}/join`, payload)
    showJoinModal.value = false
    joinForm.value = { team_name: '', join_code: '' }
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

// Auto-switch pool tab based on pick type
watch(currentPick, (pick) => {
  if (!pick || pick.user_id !== myUserId.value) return
  poolTab.value = pick.is_goalie_pick ? 'goalies' : 'skaters'
})

onMounted(async () => {
  await loadLeague()
  // Pre-fill join code if arriving from private league card
  const urlCode = route.query.join_code
  if (urlCode && league.value?.is_private && !league.value?.is_member) {
    joinForm.value.join_code = String(urlCode).toUpperCase()
    showJoinModal.value = true
  }
  if (league.value && !['forming'].includes(league.value.status)) {
    await Promise.all([loadDraftQueue(), loadPool()])
  }
})
</script>
