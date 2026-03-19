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
        :class="{ 'tab-active': activeTab === 'launch' }"
        @click="activeTab = 'launch'"
      >
        🏒 Launch Season
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
              <div>
                <div class="font-semibold text-lg">
                  {{ claim.user_display_name }}
                  <span class="text-sm text-base-content/50 ml-2">{{ claim.user_email }}</span>
                </div>
                <div class="text-sm mt-1">
                  🏒 Claims:
                  <span class="font-medium">
                    {{ claim.profile_snapshot?.first_name }} {{ claim.profile_snapshot?.last_name }}
                  </span>
                  <span v-if="claim.profile_snapshot?.orgs?.length" class="text-base-content/60 ml-2">
                    @ {{ claim.profile_snapshot.orgs.join(', ') }}
                  </span>
                </div>
                <div class="text-xs text-base-content/40 mt-1">
                  Claimed {{ formatDate(claim.claimed_at) }} · HB ID: {{ claim.hb_human_id }}
                </div>
              </div>
              <!-- Right: status badge -->
              <div>
                <span class="badge badge-warning">pending review</span>
              </div>
            </div>

            <!-- Note + action buttons -->
            <div class="mt-4 flex flex-wrap gap-3 items-end">
              <textarea
                v-model="reviewNotes[claim.id]"
                class="textarea textarea-bordered text-sm flex-1 min-w-48"
                rows="2"
                placeholder="Optional admin note..."
              ></textarea>
              <div class="flex gap-2">
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
    <div v-if="activeTab === 'launch'">
      <div class="card bg-base-200 shadow-md">
        <div class="card-body p-4">
          <h2 class="card-title text-base mb-4">🏒 Launch Fantasy Season</h2>

          <div class="flex flex-wrap gap-3 mb-4 items-end">
            <div class="form-control">
              <label class="label py-1"><span class="label-text text-xs">Org ID</span></label>
              <input v-model.number="launchOrgId" type="number" class="input input-bordered input-sm w-24" min="1" />
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
            ✅ Launched {{ launchResult.count }} league(s):
            <span v-for="l in launchResult.updated" :key="l.id" class="badge badge-sm ml-1">{{ l.name }}</span>
          </div>

          <button @click="launchSeason" class="btn btn-primary btn-sm"
            :disabled="!selectedLevelIds.length || !launchStartDate || launching">
            <span v-if="launching" class="loading loading-spinner loading-xs"></span>
            🚀 Launch Season
          </button>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useUserStore } from '@/stores/user'
import { useApiClient } from '@/api/client'

const userStore = useUserStore()
const api = useApiClient()

const isSuperAdmin = computed(() => userStore.predUser?.id === 17)
const activeTab = ref('pending')

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
})

// ── Launch Fantasy Season ──────────────────────────────────────────────────
const launchOrgId = ref(1)
const launchStartDate = ref('')
const launchActiveOnly = ref(true)
const levels = ref([])
const selectedLevelIds = ref([])
const levelsLoading = ref(false)
const launching = ref(false)
const launchError = ref(null)
const launchResult = ref(null)

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
