<template>
  <div class="container mx-auto px-4 py-8 max-w-7xl">
    <h1 class="text-3xl font-bold mb-6">🛡️ Admin Panel</h1>

    <!-- Tabs -->
    <div class="tabs tabs-boxed mb-6">
      <button
        class="tab"
        :class="{ 'tab-active': activeTab === 'pending' }"
        @click="activeTab = 'pending'"
      >
        Pending Claims
        <span v-if="pendingCount" class="badge badge-error badge-sm ml-2">{{ pendingCount }}</span>
      </button>
      <button
        class="tab"
        :class="{ 'tab-active': activeTab === 'all-claims' }"
        @click="activeTab = 'all-claims'"
      >
        All Claims
      </button>
      <button
        class="tab"
        :class="{ 'tab-active': activeTab === 'users' }"
        @click="activeTab = 'users'"
      >
        Users
      </button>
      <button
        class="tab"
        :class="{ 'tab-active': activeTab === 'analytics' }"
        @click="activeTab = 'analytics'; loadAnalytics()"
      >📊 Analytics</button>
      <button
        class="tab"
        :class="{ 'tab-active': activeTab === 'chat' }"
        @click="activeTab = 'chat'; loadChatQuestions()"
      >💬 Chat Questions</button>
      <button
        class="tab"
        :class="{ 'tab-active': activeTab === 'launch' }"
        @click="activeTab = 'launch'"
      >
        🏒 Fantasy
      </button>
    </div>

    <!-- ── Pending Claims ────────────────────────────────────────────────── -->
    <div v-if="activeTab === 'pending'">
      <div v-if="pendingLoading" class="flex justify-center py-12">
        <span class="loading loading-spinner loading-lg text-primary"></span>
      </div>
      <div v-else-if="pendingClaims.length === 0" class="text-center py-12 text-base-content/50">
        ✅ No pending claims to review.
      </div>
      <div v-else class="space-y-4">
        <div
          v-for="claim in pendingClaims"
          :key="claim.id"
          class="card bg-base-200 shadow-md border border-warning/30"
        >
          <div class="card-body">
            <div class="flex flex-wrap gap-4 justify-between">
              <!-- Left: claim info -->
              <div class="space-y-1">
                <div class="text-sm">
                  <span class="font-bold">{{ claim.review_context?.login_name || claim.user_display_name }}</span>
                  <span class="text-base-content/40 ml-1">({{ claim.user_email }})</span>
                  wants to be
                  <span class="font-bold text-primary">{{ claim.review_context?.claimed_name || (claim.profile_snapshot?.first_name + ' ' + claim.profile_snapshot?.last_name) }}</span>
                  <span v-if="claim.profile_snapshot?.orgs?.length" class="text-base-content/40 ml-1">@ {{ claim.profile_snapshot.orgs[0] }}</span>
                </div>
                <div v-if="claim.review_context?.is_manual_search" class="text-xs text-warning">
                  ⚠️ Searched by name — login didn't match
                </div>
                <div v-if="claim.review_context?.conflict_with" class="text-xs text-error">
                  🔴 Already claimed by {{ claim.review_context.conflict_with.user_display_name }}
                </div>
                <div class="text-xs text-base-content/30">{{ formatDate(claim.claimed_at) }} · HB ID {{ claim.hb_human_id }}</div>
              </div>
              <!-- Right: status badge -->
              <div>
                <span class="badge badge-warning">pending review</span>
              </div>
            </div>

            <!-- Action buttons -->
            <div class="mt-4 flex gap-2">
              <button
                class="btn btn-success btn-sm"
                :disabled="reviewLoading[claim.id]"
                @click="approve(claim.id)"
              >
                <span v-if="reviewLoading[claim.id]" class="loading loading-spinner loading-xs"></span>
                ✅ Approve
              </button>
              <button
                class="btn btn-error btn-sm"
                :disabled="reviewLoading[claim.id]"
                @click="reject(claim.id)"
              >
                <span v-if="reviewLoading[claim.id]" class="loading loading-spinner loading-xs"></span>
                ❌ Reject
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── All Claims ─────────────────────────────────────────────────────── -->
    <div v-if="activeTab === 'all-claims'">
      <div class="flex gap-3 mb-4">
        <select v-model="claimsStatusFilter" class="select select-bordered select-sm" @change="loadAllClaims">
          <option value="all">All statuses</option>
          <option value="confirmed">Confirmed</option>
          <option value="pending_review">Pending Review</option>
          <option value="rejected">Rejected</option>
        </select>
        <button class="btn btn-sm btn-ghost" @click="loadAllClaims">🔄 Refresh</button>
      </div>

      <div v-if="allClaimsLoading" class="flex justify-center py-12">
        <span class="loading loading-spinner loading-lg text-primary"></span>
      </div>
      <div v-else>
        <div class="overflow-x-auto">
          <table class="table table-zebra w-full text-sm">
            <thead>
              <tr>
                <th>ID</th>
                <th>User</th>
                <th>HB Player</th>
                <th>Orgs</th>
                <th>Claimed</th>
                <th>Status</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in allClaims" :key="c.id">
                <td>{{ c.id }}</td>
                <td>
                  <div class="font-medium">{{ c.user_display_name }}</div>
                  <div class="text-xs opacity-50">{{ c.user_email }}</div>
                </td>
                <td>{{ c.profile_snapshot?.first_name }} {{ c.profile_snapshot?.last_name }}</td>
                <td class="text-xs">{{ (c.profile_snapshot?.orgs || []).join(', ') || '—' }}</td>
                <td class="text-xs">{{ formatDate(c.claimed_at) }}</td>
                <td>
                  <span class="badge badge-sm" :class="statusBadge(c.claim_status)">
                    {{ c.claim_status }}
                  </span>
                </td>
                <td class="text-xs text-base-content/60">{{ c.admin_note || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="text-sm text-base-content/50 mt-2">{{ allClaims.length }} claims</div>
      </div>
    </div>

    <!-- ── Users ──────────────────────────────────────────────────────────── -->
    <div v-if="activeTab === 'users'">
      <div class="flex gap-3 mb-4">
        <button class="btn btn-sm btn-ghost" @click="loadUsers">🔄 Refresh</button>
      </div>

      <div v-if="usersLoading" class="flex justify-center py-12">
        <span class="loading loading-spinner loading-lg text-primary"></span>
      </div>
      <div v-else>
        <div class="overflow-x-auto">
          <table class="table table-zebra w-full text-sm">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Email</th>
                <th>Admin</th>
                <th>Claims</th>
                <th>Joined</th>
                <th v-if="isSuperAdmin">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in users" :key="u.id">
                <td>{{ u.id }}</td>
                <td class="font-medium">{{ u.display_name }}</td>
                <td class="text-xs">{{ u.email || '—' }}</td>
                <td>
                  <span v-if="u.is_admin" class="badge badge-primary badge-sm">admin</span>
                  <span v-else class="text-base-content/30">—</span>
                </td>
                <td>{{ u.claim_count }}</td>
                <td class="text-xs">{{ formatDate(u.created_at) }}</td>
                <td v-if="isSuperAdmin">
                  <button
                    v-if="u.id !== 17"
                    class="btn btn-xs"
                    :class="u.is_admin ? 'btn-error' : 'btn-success'"
                    :disabled="toggleLoading[u.id]"
                    @click="toggleAdmin(u.id)"
                  >
                    {{ u.is_admin ? 'Revoke Admin' : 'Grant Admin' }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="text-sm text-base-content/50 mt-2">{{ users.length }} users</div>
      </div>

    </div>

    <!-- ── Launch Season tab ──────────────────────────────────────────────── -->
    <!-- ── Analytics ─────────────────────────────────────────────────────── -->
    <div v-if="activeTab === 'analytics'">
      <div v-if="analyticsLoading" class="flex justify-center py-12">
        <span class="loading loading-spinner loading-lg text-primary"></span>
      </div>
      <div v-else-if="!analyticsData" class="text-center py-12 text-base-content/50">No data yet.</div>
      <template v-else>
        <!-- Summary cards -->
        <div class="grid grid-cols-3 gap-4 mb-6">
          <div class="stat bg-base-200 rounded-xl">
            <div class="stat-title text-xs">Visits (30d)</div>
            <div class="stat-value text-primary text-2xl">{{ analyticsTotal.visit }}</div>
          </div>
          <div class="stat bg-base-200 rounded-xl">
            <div class="stat-title text-xs">Picks (30d)</div>
            <div class="stat-value text-success text-2xl">{{ analyticsTotal.pick }}</div>
          </div>
          <div class="stat bg-base-200 rounded-xl">
            <div class="stat-title text-xs">Chat msgs (30d)</div>
            <div class="stat-value text-warning text-2xl">{{ analyticsTotal.chat }}</div>
          </div>
        </div>
        <!-- Chart -->
        <div class="card bg-base-200 shadow mb-4">
          <div class="card-body p-4">
            <canvas ref="analyticsCanvas" height="120"></canvas>
          </div>
        </div>
        <!-- Daily table -->
        <div class="overflow-x-auto">
          <table class="table table-sm text-xs">
            <thead>
              <tr><th>Date</th><th class="text-primary">Visits</th><th class="text-success">Picks</th><th class="text-warning">Chat</th></tr>
            </thead>
            <tbody>
              <tr v-for="(row, day) in analyticsData" :key="day">
                <td class="font-mono">{{ day }}</td>
                <td>{{ row.visit || 0 }}</td>
                <td>{{ row.pick || 0 }}</td>
                <td>{{ row.chat || 0 }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>

    <!-- ── Chat Questions ─────────────────────────────────────────────────── -->
    <div v-if="activeTab === 'chat'">
      <div v-if="chatLoading" class="flex justify-center py-12">
        <span class="loading loading-spinner loading-lg text-primary"></span>
      </div>
      <div v-else-if="chatQuestions.length === 0" class="text-center py-12 text-base-content/50">
        No questions yet.
      </div>
      <div v-else class="space-y-2">
        <div class="text-xs text-base-content/40 mb-3">{{ chatQuestions.length }} most recent questions</div>
        <div
          v-for="q in chatQuestions"
          :key="q.id"
          class="flex items-start gap-3 rounded-xl bg-base-200 px-4 py-3"
        >
          <div class="flex-1 min-w-0">
            <div class="text-sm">{{ q.query }}</div>
            <div class="text-xs text-base-content/40 mt-1">
              {{ q.user }} · {{ formatDate(q.created_at) }}
              <span v-if="q.is_off_topic" class="badge badge-xs badge-warning ml-1">off-topic</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="activeTab === 'launch'">
      <div class="card bg-base-200 shadow-md">
        <div class="card-body p-4">
          <h2 class="card-title text-base mb-4">🏒 Launch Fantasy Season</h2>

          <div class="flex flex-wrap gap-3 mb-4 items-end">
            <div class="form-control">
              <label class="label py-1"><span class="label-text text-xs">Organization</span></label>
              <select v-model.number="launchOrgId" class="select select-bordered select-sm w-48">
                <option v-for="org in orgs" :key="org.id" :value="org.id">{{ org.name }}</option>
              </select>
            </div>
            <div class="form-control">
              <label class="label py-1"><span class="label-text text-xs">Season Start Date</span></label>
              <input v-model="launchStartDate" type="date" class="input input-bordered input-sm" />
            </div>
            <div class="form-control">
              <label class="label cursor-pointer gap-2 py-1">
                <span class="label-text text-xs">Active levels only</span>
                <input type="checkbox" v-model="launchActiveOnly" class="checkbox checkbox-sm" />
              </label>
            </div>
            <button @click="loadLevels" class="btn btn-sm btn-outline mt-5" :disabled="levelsLoading">
              <span v-if="levelsLoading" class="loading loading-spinner loading-xs"></span>
              Load Levels
            </button>
          </div>

          <div v-if="levels.length" class="mb-4">
            <div class="text-xs text-base-content/60 mb-2">Select levels to launch ({{ selectedLevelIds.length }} selected):</div>
            <div class="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-64 overflow-y-auto">
              <label v-for="lvl in levels" :key="lvl.level_id" class="flex items-center gap-2 cursor-pointer p-2 rounded hover:bg-base-300">
                <input type="checkbox" class="checkbox checkbox-sm checkbox-primary"
                  :value="lvl.level_id" v-model="selectedLevelIds" />
                <span class="text-sm">{{ lvl.short_name || lvl.level_name }}</span>
              </label>
            </div>
            <div class="flex gap-2 mt-2">
              <button @click="selectedLevelIds = levels.map(l => l.level_id)" class="btn btn-xs btn-ghost">Select all</button>
              <button @click="selectedLevelIds = []" class="btn btn-xs btn-ghost">Clear</button>
            </div>
          </div>

          <div v-if="launchError" class="alert alert-error text-sm mb-3">{{ launchError }}</div>
          <div v-if="launchResult" class="alert alert-success text-sm mb-3">
            ✅ Done — {{ launchResult.created }} created, {{ launchResult.updated }} updated.
            <div class="mt-1 flex flex-wrap gap-1">
              <span v-for="l in launchResult.leagues" :key="l.id"
                class="badge badge-sm"
                :class="l.action === 'created' ? 'badge-primary' : 'badge-ghost'">
                {{ l.name }} ({{ l.action }})
              </span>
            </div>
          </div>

          <button @click="launchSeason" class="btn btn-primary btn-sm"
            :disabled="!selectedLevelIds.length || !launchStartDate || launching">
            <span v-if="launching" class="loading loading-spinner loading-xs"></span>
            🚀 Launch Season
          </button>
        </div>
      </div>

      <!-- ── League List & Delete ──────────────────────────────────────── -->
      <div class="card bg-base-200 shadow-md mt-4">
        <div class="card-body p-4">
          <div class="flex items-center justify-between mb-3">
            <h2 class="card-title text-base">📋 All Leagues</h2>
            <button @click="loadAdminLeagues" class="btn btn-xs btn-ghost" :disabled="adminLeaguesLoading">
              <span v-if="adminLeaguesLoading" class="loading loading-spinner loading-xs"></span>
              Refresh
            </button>
          </div>

          <div v-if="!adminLeagues.length" class="text-sm text-base-content/50 py-4 text-center">
            No leagues found. Change org or click Refresh.
          </div>

          <div v-else class="overflow-x-auto">
            <table class="table table-xs w-full">
              <thead>
                <tr>
                  <th>
                    <input type="checkbox" class="checkbox checkbox-xs"
                      :checked="selectedLeagueIds.length === adminLeagues.length && adminLeagues.length > 0"
                      @change="e => selectedLeagueIds = e.target.checked ? adminLeagues.map(l => l.id) : []" />
                  </th>
                  <th>Name</th>
                  <th>Level</th>
                  <th>Status</th>
                  <th>Managers</th>
                  <th>Season Starts</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="l in adminLeagues" :key="l.id" class="hover">
                  <td>
                    <input type="checkbox" class="checkbox checkbox-xs"
                      :value="l.id" v-model="selectedLeagueIds" />
                  </td>
                  <td class="font-medium">{{ l.name }}</td>
                  <td>{{ l.level_name }}</td>
                  <td><span class="badge badge-xs" :class="statusBadgeClass(l.status)">{{ l.status }}</span></td>
                  <td>{{ l.manager_count ?? '—' }}</td>
                  <td class="text-xs">{{ l.season_starts_at ? new Date(l.season_starts_at).toLocaleDateString() : '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Batch delete -->
          <div v-if="selectedLeagueIds.length" class="flex items-center gap-3 mt-3">
            <span class="text-sm text-base-content/70">{{ selectedLeagueIds.length }} selected</span>
            <button v-if="!confirmBatchDelete" @click="confirmBatchDelete = true" class="btn btn-xs btn-error">
              🗑 Delete selected
            </button>
            <template v-else>
              <span class="text-sm text-error font-semibold">Delete {{ selectedLeagueIds.length }} league(s) and ALL their data?</span>
              <button @click="batchDeleteLeagues" class="btn btn-xs btn-error" :disabled="deleting">
                <span v-if="deleting" class="loading loading-spinner loading-xs"></span>
                Yes, delete
              </button>
              <button @click="confirmBatchDelete = false" class="btn btn-xs btn-ghost">Cancel</button>
            </template>
          </div>
          <div v-if="deleteResult" class="alert mt-2 text-sm" :class="deleteResult.startsWith('✅') ? 'alert-success' : 'alert-error'">{{ deleteResult }}</div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useUserStore } from '@/stores/user'
import { useApiClient } from '@/api/client'

const userStore = useUserStore()
const api = useApiClient()

const isSuperAdmin = computed(() => userStore.predUser?.id === 17)
const activeTab = ref('pending')

const analyticsData = ref(null)
const analyticsLoading = ref(false)
const analyticsCanvas = ref(null)
let analyticsChart = null

const analyticsTotal = computed(() => {
  if (!analyticsData.value) return { visit: 0, pick: 0, chat: 0 }
  return Object.values(analyticsData.value).reduce(
    (acc, row) => ({ visit: acc.visit + (row.visit||0), pick: acc.pick + (row.pick||0), chat: acc.chat + (row.chat||0) }),
    { visit: 0, pick: 0, chat: 0 }
  )
})

function renderAnalyticsChart(data) {
  nextTick(() => {
    if (!analyticsCanvas.value || !window.Chart) return
    if (analyticsChart) analyticsChart.destroy()
    const labels = Object.keys(data).sort()
    analyticsChart = new window.Chart(analyticsCanvas.value, {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: 'Visits',  data: labels.map(d => data[d]?.visit || 0), borderColor: '#38bdf8', backgroundColor: '#38bdf820', tension: 0.3, fill: true },
          { label: 'Picks',   data: labels.map(d => data[d]?.pick  || 0), borderColor: '#4ade80', backgroundColor: '#4ade8020', tension: 0.3, fill: true },
          { label: 'Chat',    data: labels.map(d => data[d]?.chat  || 0), borderColor: '#fbbf24', backgroundColor: '#fbbf2420', tension: 0.3, fill: true },
        ]
      },
      options: {
        responsive: true,
        plugins: { legend: { labels: { color: '#94a3b8' } } },
        scales: {
          x: { ticks: { color: '#64748b', maxTicksLimit: 10 }, grid: { color: '#1e293b' } },
          y: { ticks: { color: '#64748b' }, grid: { color: '#1e293b' }, beginAtZero: true }
        }
      }
    })
  })
}

async function loadAnalytics() {
  if (analyticsData.value) return
  analyticsLoading.value = true
  try {
    // Load Chart.js from CDN if not already loaded
    if (!window.Chart) {
      await new Promise((resolve, reject) => {
        const s = document.createElement('script')
        s.src = 'https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js'
        s.onload = resolve; s.onerror = reject
        document.head.appendChild(s)
      })
    }
    const { data } = await api.get('/api/admin/analytics?days=30')
    analyticsData.value = data.data || {}
    renderAnalyticsChart(analyticsData.value)
  } catch (e) {
    console.error('Failed to load analytics', e)
  } finally {
    analyticsLoading.value = false
  }
}

const chatQuestions = ref([])
const chatLoading = ref(false)
async function loadChatQuestions() {
  if (chatQuestions.value.length) return
  chatLoading.value = true
  try {
    const { data } = await api.get('/api/admin/chat/questions?limit=200')
    chatQuestions.value = data.questions || []
  } catch (e) {
    console.error('Failed to load chat questions', e)
  } finally {
    chatLoading.value = false
  }
}

// ── Pending Claims ───────────────────────────────────────────────────────────
const pendingClaims = ref([])
const pendingLoading = ref(false)
const pendingCount = computed(() => pendingClaims.value.length)
const reviewNotes = ref({})
const reviewLoading = ref({})

async function loadPendingClaims() {
  pendingLoading.value = true
  try {
    const { data } = await api.get('/api/admin/claims?status=pending_review')
    pendingClaims.value = data.claims || []
  } catch (e) {
    console.error('Failed to load pending claims', e)
  } finally {
    pendingLoading.value = false
  }
}

async function approve(claimId) {
  reviewLoading.value[claimId] = true
  try {
    await api.post(`/api/admin/claims/${claimId}/approve`, { note: reviewNotes.value[claimId] || null })
    pendingClaims.value = pendingClaims.value.filter(c => c.id !== claimId)
  } catch (e) {
    alert('Failed to approve: ' + (e.response?.data?.message || e.message))
  } finally {
    reviewLoading.value[claimId] = false
  }
}

async function reject(claimId) {
  reviewLoading.value[claimId] = true
  try {
    await api.post(`/api/admin/claims/${claimId}/reject`, { note: reviewNotes.value[claimId] || null })
    pendingClaims.value = pendingClaims.value.filter(c => c.id !== claimId)
  } catch (e) {
    alert('Failed to reject: ' + (e.response?.data?.message || e.message))
  } finally {
    reviewLoading.value[claimId] = false
  }
}

// ── All Claims ───────────────────────────────────────────────────────────────
const allClaims = ref([])
const allClaimsLoading = ref(false)
const claimsStatusFilter = ref('all')

async function loadAllClaims() {
  allClaimsLoading.value = true
  try {
    const { data } = await api.get(`/api/admin/claims?status=${claimsStatusFilter.value}`)
    allClaims.value = data.claims || []
  } catch (e) {
    console.error('Failed to load all claims', e)
  } finally {
    allClaimsLoading.value = false
  }
}

// ── Users ────────────────────────────────────────────────────────────────────
const users = ref([])
const usersLoading = ref(false)
const toggleLoading = ref({})

async function loadUsers() {
  usersLoading.value = true
  try {
    const { data } = await api.get('/api/admin/users')
    users.value = data.users || []
  } catch (e) {
    console.error('Failed to load users', e)
  } finally {
    usersLoading.value = false
  }
}

async function toggleAdmin(userId) {
  toggleLoading.value[userId] = true
  try {
    const { data } = await api.post(`/api/admin/users/${userId}/toggle-admin`)
    const u = users.value.find(x => x.id === userId)
    if (u) u.is_admin = data.is_admin
  } catch (e) {
    alert('Failed to toggle admin: ' + (e.response?.data?.message || e.message))
  } finally {
    toggleLoading.value[userId] = false
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function statusBadgeClass(s) {
  return { forming: 'badge-info', draft_open: 'badge-warning', drafting: 'badge-warning', active: 'badge-success', completed: 'badge-neutral' }[s] || 'badge-ghost'
}

function statusBadge(status) {
  switch (status) {
    case 'confirmed': return 'badge-success'
    case 'pending_review': return 'badge-warning'
    case 'rejected': return 'badge-error'
    default: return 'badge-ghost'
  }
}

// Load data on mount and tab change
onMounted(() => {
  loadPendingClaims()
})

watch(activeTab, (tab) => {
  if (tab === 'pending') loadPendingClaims()
  else if (tab === 'all-claims') loadAllClaims()
  else if (tab === 'users') loadUsers()
  else if (tab === 'launch') loadOrgs()
})

// ── Launch Fantasy Season ──────────────────────────────────────────────────
const orgs = ref([])
const launchOrgId = ref(1)

watch(launchOrgId, () => {
  if (activeTab.value === 'launch') {
    loadLevels()
    loadAdminLeagues()
  }
})

async function loadOrgs() {
  try {
    const { data } = await api.get('/api/admin/fantasy/orgs')
    orgs.value = data.orgs
    if (orgs.value.length && !orgs.value.find(o => o.id === launchOrgId.value)) {
      launchOrgId.value = orgs.value[0].id
    }
    // Auto-load levels and leagues for the default org
    await loadLevels()
    await loadAdminLeagues()
  } catch { /* ignore */ }
}
const launchStartDate = ref('')
const launchActiveOnly = ref(true)
const levels = ref([])
const selectedLevelIds = ref([])
const levelsLoading = ref(false)
const launching = ref(false)
const launchError = ref(null)
const launchResult = ref(null)

// ── Admin League List & Delete ─────────────────────────────────────────────
const adminLeagues = ref([])
const adminLeaguesLoading = ref(false)
const selectedLeagueIds = ref([])
const confirmBatchDelete = ref(false)
const deleting = ref(false)
const deleteResult = ref(null)

async function loadAdminLeagues() {
  adminLeaguesLoading.value = true
  selectedLeagueIds.value = []
  confirmBatchDelete.value = false
  deleteResult.value = null
  try {
    const { data } = await api.get(`/api/admin/fantasy/leagues?org_id=${launchOrgId.value}`)
    adminLeagues.value = data.leagues
  } catch { /* ignore */ } finally {
    adminLeaguesLoading.value = false
  }
}

async function batchDeleteLeagues() {
  if (!selectedLeagueIds.value.length) return
  deleting.value = true
  try {
    const { data } = await api.post('/api/admin/fantasy/leagues/batch-delete', {
      league_ids: selectedLeagueIds.value,
    })
    deleteResult.value = `✅ Deleted ${data.deleted} league(s): ${data.names.join(', ')}`
    selectedLeagueIds.value = []
    confirmBatchDelete.value = false
    await loadAdminLeagues()
  } catch (e) {
    deleteResult.value = `❌ ${e.response?.data?.message || e.message}`
  } finally {
    deleting.value = false
  }
}

async function loadLevels() {
  levelsLoading.value = true
  launchError.value = null
  levels.value = []
  selectedLevelIds.value = []
  try {
    const { data } = await api.get('/api/admin/fantasy/active-levels', {
      params: { org_id: launchOrgId.value, active_only: launchActiveOnly.value }
    })
    levels.value = data.levels
  } catch (e) {
    launchError.value = e.response?.data?.message || e.message
  } finally {
    levelsLoading.value = false
  }
}

async function launchSeason() {
  launching.value = true
  launchError.value = null
  launchResult.value = null
  try {
    const { data } = await api.post('/api/admin/fantasy/launch-season', {
      org_id: launchOrgId.value,
      level_ids: selectedLevelIds.value,
      season_start_date: launchStartDate.value,
    })
    launchResult.value = data
    selectedLevelIds.value = []
  } catch (e) {
    launchError.value = e.response?.data?.message || e.message
  } finally {
    launching.value = false
  }
}
</script>
