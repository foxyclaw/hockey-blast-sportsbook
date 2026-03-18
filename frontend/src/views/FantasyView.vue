<template>
  <div class="max-w-4xl mx-auto px-4 py-6">
    <!-- Header -->
    <div class="mb-6 flex items-start justify-between flex-wrap gap-4">
      <div>
        <h1 class="text-2xl font-extrabold tracking-tight">🏒 Fantasy Hockey</h1>
        <p class="text-base-content/60 text-sm mt-1">Draft players, score points, win glory.</p>
      </div>
      <button class="btn btn-primary btn-sm" @click="showCreateModal = true">
        + Create League
      </button>
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
            class="card bg-base-200 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
            @click="$router.push(`/fantasy/${league.id}`)"
          >
            <div class="card-body p-4">
              <div class="flex items-start justify-between gap-2">
                <div>
                  <h3 class="font-bold text-base">{{ league.name }}</h3>
                  <p class="text-xs text-base-content/50">Level: {{ league.level_name }}</p>
                  <p v-if="league.season_label" class="text-xs text-base-content/50">{{ league.season_label }}</p>
                </div>
                <span class="badge badge-sm" :class="statusBadgeClass(league.status)">
                  {{ statusLabel(league.status) }}
                </span>
              </div>
              <div class="flex items-center gap-4 mt-3 text-xs text-base-content/60">
                <span>👥 {{ league.manager_count }} / {{ league.max_managers }} managers</span>
                <span v-if="league.is_member" class="badge badge-xs badge-success">Joined</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create League Modal -->
    <div v-if="showCreateModal" class="modal modal-open">
      <div class="modal-box max-w-md">
        <h3 class="font-bold text-lg mb-4">Create Fantasy League</h3>

        <form @submit.prevent="createLeague" class="space-y-4">
          <div class="form-control">
            <label class="label"><span class="label-text text-sm">League Name</span></label>
            <input
              v-model="createForm.name"
              type="text"
              placeholder="e.g. Pond Puck Pros"
              class="input input-bordered input-sm"
              required
            />
          </div>

          <div class="form-control">
            <label class="label"><span class="label-text text-sm">Your Team Name</span></label>
            <input
              v-model="createForm.team_name"
              type="text"
              placeholder="e.g. Ice Bandits"
              class="input input-bordered input-sm"
              required
            />
          </div>

          <div class="form-control">
            <label class="label"><span class="label-text text-sm">Level</span></label>
            <select v-model="createForm.level_id" class="select select-bordered select-sm" required>
              <option value="" disabled>Select a level...</option>
              <option v-for="lvl in levels" :key="lvl.level_id" :value="lvl.level_id">
                {{ lvl.level_name }} (up to {{ lvl.max_managers }} managers)
              </option>
            </select>
            <div v-if="levelsLoading" class="text-xs text-base-content/40 mt-1">Loading levels…</div>
          </div>

          <div class="form-control">
            <label class="label"><span class="label-text text-sm">Season Label (optional)</span></label>
            <input
              v-model="createForm.season_label"
              type="text"
              placeholder="e.g. Spring 2026"
              class="input input-bordered input-sm"
            />
          </div>

          <div v-if="createError" class="alert alert-error text-sm py-2">{{ createError }}</div>

          <div class="modal-action mt-2">
            <button type="button" class="btn btn-ghost btn-sm" @click="showCreateModal = false">Cancel</button>
            <button type="submit" class="btn btn-primary btn-sm" :disabled="creating">
              <span v-if="creating" class="loading loading-spinner loading-xs"></span>
              Create
            </button>
          </div>
        </form>
      </div>
      <div class="modal-backdrop" @click="showCreateModal = false"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApiClient } from '@/api/client'

const router = useRouter()
const api = useApiClient()

const leagues = ref([])
const loading = ref(true)
const levels = ref([])
const levelsLoading = ref(false)

const showCreateModal = ref(false)
const creating = ref(false)
const createError = ref('')
const createForm = ref({ name: '', team_name: '', level_id: '', season_label: '' })

const STATUS_ORDER = ['forming', 'draft_open', 'drafting', 'active', 'completed']
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

const groupedLeagues = computed(() => {
  const groups = {}
  for (const league of leagues.value) {
    const label = STATUS_LABELS[league.status] || league.status
    if (!groups[label]) groups[label] = []
    groups[label].push(league)
  }
  return Object.entries(groups).map(([label, ls]) => ({ label, leagues: ls }))
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

async function loadLevels() {
  levelsLoading.value = true
  try {
    const { data } = await api.get('/api/fantasy/levels')
    levels.value = data.levels || []
  } catch {
    levels.value = []
  } finally {
    levelsLoading.value = false
  }
}

async function createLeague() {
  createError.value = ''
  creating.value = true
  try {
    const { data } = await api.post('/api/fantasy/leagues', {
      name: createForm.value.name,
      team_name: createForm.value.team_name,
      level_id: createForm.value.level_id,
      season_label: createForm.value.season_label || undefined,
    })
    showCreateModal.value = false
    createForm.value = { name: '', team_name: '', level_id: '', season_label: '' }
    router.push(`/fantasy/${data.id}`)
  } catch (e) {
    createError.value = e?.response?.data?.message || 'Failed to create league'
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  loadLeagues()
  loadLevels()
})
</script>
