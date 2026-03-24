<template>
  <div class="max-w-4xl mx-auto px-4 py-6">
    <!-- Draft announcement banner -->
    <div class="rounded-xl bg-primary/10 border-2 border-primary/40 px-5 py-4 mb-6 flex items-center gap-4">
      <span class="text-3xl">📣</span>
      <div>
        <div class="font-extrabold text-base-content text-lg leading-tight">Fantasy Draft kicks off Friday March 27 at 7:00 PM — runs all weekend!</div>
        <div class="text-sm text-base-content/60 mt-0.5">Join or create your league now so you're ready. Season starts April 1.</div>
      </div>
    </div>

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
            class="card bg-base-200 shadow-sm hover:shadow-md transition-shadow"
          >
            <div class="card-body p-4">
              <div class="flex items-start justify-between gap-2 cursor-pointer" @click="$router.push(`/fantasy/${league.id}`)">
                <div>
                  <div class="flex items-center gap-2">
                    <h3 class="font-bold text-base">{{ league.name }}</h3>
                    <span v-if="league.is_private" class="badge badge-xs badge-neutral gap-1">🔒 Private</span>
                  </div>
                  <p class="text-xs text-base-content/50">Level: {{ league.level_name }}</p>
                  <p v-if="league.season_label" class="text-xs text-base-content/50">{{ league.season_label }}</p>
                </div>
                <span class="badge badge-sm" :class="statusBadgeClass(league.status)">
                  {{ statusLabel(league.status) }}
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

    <!-- Create League Modal -->
    <div v-if="showCreateModal" class="modal modal-open">
      <div class="modal-box max-w-md">
        <h3 class="font-bold text-lg mb-4">Create Fantasy League</h3>

        <form @submit.prevent="createLeague" class="space-y-4">
          <!-- Season (hardcoded to current upcoming season) -->
          <div class="form-control">
            <label class="label"><span class="label-text text-sm">League</span></label>
            <select class="select select-bordered select-sm" disabled>
              <option selected>Sharks Ice Adult Hockey League — Spring 2026</option>
            </select>
            <div class="text-xs text-base-content/40 mt-1">Season starts April 1, 2026 · Draft: Mar 27–29</div>
          </div>

          <div class="form-control">
            <label class="label"><span class="label-text text-sm">Your Level</span></label>
            <select v-model="createForm.level_id" class="select select-bordered select-sm" required>
              <option value="" disabled>Select your level...</option>
              <option v-for="lvl in levels" :key="lvl.level_id" :value="lvl.level_id">
                Level {{ lvl.level_name }}
              </option>
            </select>
            <div v-if="levelsLoading" class="text-xs text-base-content/40 mt-1">Loading levels…</div>
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
            <label class="label cursor-pointer justify-start gap-3">
              <input type="checkbox" v-model="createForm.is_private" class="toggle toggle-sm" />
              <span class="label-text text-sm">🔒 Private league (invite only)</span>
            </label>
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

const router = useRouter()
const api = useApiClient()

const leagues = ref([])
const loading = ref(true)
const levels = ref([])
const levelsLoading = ref(false)

const showCreateModal = ref(false)
const creating = ref(false)
const createError = ref('')
const createForm = ref({ team_name: '', level_id: '', is_private: false })
const createdJoinCode = ref('')
const showJoinCodeModal = ref(false)

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
  return Object.entries(groups).map(([label, ls]) => ({
    label,
    leagues: ls.slice().sort((a, b) => (a.name || '').localeCompare(b.name || ''))
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

async function loadLevels() {
  levelsLoading.value = true
  try {
    const { data } = await api.get('/api/fantasy/levels')
    levels.value = (data.levels || []).sort((a, b) => a.level_name.localeCompare(b.level_name, undefined, {numeric: true, sensitivity: "base"}))
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
    // Find selected level name for the league name
    const lvl = levels.value.find(l => l.level_id === createForm.value.level_id)
    const levelLabel = lvl ? `Level ${lvl.level_name}` : `Level ${createForm.value.level_id}`
    const { data } = await api.post('/api/fantasy/leagues', {
      name: `${levelLabel} — Spring 2026`,
      team_name: createForm.value.team_name,
      level_id: createForm.value.level_id,
      season_label: 'Spring 2026',
      is_private: createForm.value.is_private,
      season_starts_at: '2026-04-01',
      draft_opens_at: '2026-03-27T19:00',
      draft_closes_at: '2026-03-29T23:00',
    })
    showCreateModal.value = false
    if (data.is_private && data.join_code) {
      createdJoinCode.value = data.join_code
      showJoinCodeModal.value = true
      // Navigate after a moment
      setTimeout(() => router.push(`/fantasy/${data.id}`), 0)
    } else {
      router.push(`/fantasy/${data.id}`)
    }
    createForm.value = { team_name: '', level_id: '', is_private: false }
  } catch (e) {
    createError.value = e?.response?.data?.message || 'Failed to create league'
  } finally {
    creating.value = false
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
  loadLevels()
})
</script>
