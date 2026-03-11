<template>
  <div class="container mx-auto px-4 py-6 max-w-2xl">
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-primary">🏒 Find Yourself</h1>
      <p class="text-base-content/60 mt-1 text-sm">
        Link your account to your hockey history for personalized stats and captain tools.
      </p>
    </div>

    <!-- Existing claims -->
    <div v-if="existingClaims.length" class="mb-6">
      <h2 class="text-sm font-semibold text-base-content/70 uppercase mb-2">Linked Profiles</h2>
      <div class="space-y-2">
        <div
          v-for="claim in existingClaims"
          :key="claim.hb_human_id"
          class="card bg-base-200 p-4 flex flex-row items-center gap-3"
        >
          <span class="text-2xl">✅</span>
          <div>
            <div class="font-medium">{{ claim.profile?.first_name }} {{ claim.profile?.last_name }}</div>
            <div class="text-xs text-base-content/50">
              {{ claim.profile?.orgs?.join(', ') }} ·
              {{ claim.profile?.first_date }} – {{ claim.profile?.last_date }}
            </div>
          </div>
          <div v-if="claim.is_primary" class="badge badge-primary badge-sm ml-auto">Primary</div>
        </div>
      </div>
      <button class="btn btn-ghost btn-sm mt-2" @click="showSearch = true">+ Add another profile</button>
    </div>

    <!-- Search form -->
    <div v-if="!existingClaims.length || showSearch" class="card bg-base-200 shadow-lg p-6 mb-6">
      <h2 class="font-semibold mb-3">Search the hockey database</h2>
      <div class="flex gap-2">
        <input
          v-model="searchName"
          type="text"
          placeholder="Your name (e.g. Pavel Kletskov)"
          class="input input-bordered flex-1"
          @keyup.enter="search"
        />
        <button class="btn btn-primary" :class="{ loading: searching }" @click="search">
          Search
        </button>
      </div>
    </div>

    <!-- Candidates -->
    <div v-if="candidates.length" class="space-y-4 mb-6">
      <h2 class="text-sm font-semibold text-base-content/70 uppercase">
        {{ candidates.length }} match{{ candidates.length !== 1 ? 'es' : '' }} found
      </h2>

      <div
        v-for="c in candidates"
        :key="c.hb_human_id"
        class="card bg-base-200 shadow border-2 transition-all cursor-pointer"
        :class="selected.includes(c.hb_human_id) ? 'border-primary' : 'border-transparent'"
        @click="toggleSelect(c.hb_human_id)"
      >
        <div class="card-body p-4">
          <div class="flex items-start justify-between gap-2">
            <div>
              <div class="font-bold text-lg">{{ c.first_name }} {{ c.last_name }}</div>
              <div class="text-xs text-base-content/50 mt-0.5">
                {{ c.orgs?.join(', ') || 'Unknown org' }}
              </div>
            </div>
            <!-- Skill badge -->
            <div class="flex flex-col items-end gap-1">
              <div
                v-if="c.skill_value != null"
                class="badge badge-sm"
                :class="skillBadgeClass(c.skill_value)"
              >
                {{ skillLabel(c.skill_value) }}
              </div>
              <div v-if="selected.includes(c.hb_human_id)" class="badge badge-primary badge-sm">✓ Selected</div>
            </div>
          </div>

          <!-- Career dates -->
          <div class="text-xs text-base-content/60 mt-2">
            🗓 Played {{ c.first_date }} – {{ c.last_date }}
          </div>

          <!-- Teams (most recent 5) -->
          <div v-if="c.teams?.length" class="mt-2">
            <div class="text-xs text-base-content/50 mb-1">Recent teams:</div>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="t in c.teams.slice(0, 5)"
                :key="t.team_id"
                class="badge badge-ghost badge-sm"
              >
                {{ t.team_name }}
                <span v-if="t.role_type === 'C'" class="text-yellow-400 ml-0.5">©</span>
              </span>
              <span v-if="c.teams.length > 5" class="badge badge-ghost badge-sm opacity-50">
                +{{ c.teams.length - 5 }} more
              </span>
            </div>
          </div>

          <!-- Aliases -->
          <div v-if="c.aliases?.length" class="text-xs text-base-content/40 mt-1">
            Also known as: {{ c.aliases.map(a => `${a.first_name} ${a.last_name}`).join(', ') }}
          </div>
        </div>
      </div>
    </div>

    <!-- No results -->
    <div v-else-if="searched && !searching" class="text-center py-8 text-base-content/50">
      <p>No matches found for "{{ searchName }}"</p>
      <p class="text-sm mt-1">Try a shorter name or check spelling</p>
    </div>

    <!-- Actions -->
    <div class="flex flex-col gap-3">
      <button
        v-if="selected.length"
        class="btn btn-primary w-full"
        :class="{ loading: confirming }"
        @click="confirm"
      >
        ✅ This is me ({{ selected.length }} profile{{ selected.length !== 1 ? 's' : '' }})
      </button>
      <button class="btn btn-ghost w-full" @click="skip">Skip for now</button>
    </div>

    <!-- Success toast -->
    <div v-if="confirmed" class="toast toast-top toast-center z-50">
      <div class="alert alert-success">
        <span>Identity linked! Welcome to the hockey world 🏒</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth0 } from '@auth0/auth0-vue'
import { useApiClient } from "@/api/client"
const api = useApiClient()

const router = useRouter()
const { user } = useAuth0()

const searchName = ref(user.value?.name || '')
const candidates = ref([])
const selected = ref([])
const existingClaims = ref([])
const showSearch = ref(false)
const searching = ref(false)
const searched = ref(false)
const confirming = ref(false)
const confirmed = ref(false)

onMounted(async () => {
  try {
    const res = await api.get('/identity/my-claims')
    existingClaims.value = res.data.claims || []
  } catch {}
})

async function search() {
  if (!searchName.value.trim()) return
  searching.value = true
  searched.value = false
  try {
    const res = await api.get('/identity/candidates', { params: { name: searchName.value } })
    candidates.value = res.data.candidates || []
    searched.value = true
  } catch (e) {
    console.error(e)
  } finally {
    searching.value = false
  }
}

function toggleSelect(id) {
  const idx = selected.value.indexOf(id)
  if (idx === -1) selected.value.push(id)
  else selected.value.splice(idx, 1)
}

async function confirm() {
  if (!selected.value.length) return
  confirming.value = true
  try {
    await api.post('/identity/confirm', { hb_human_id: selected.value })
    confirmed.value = true
    setTimeout(() => router.push('/'), 1500)
  } catch (e) {
    console.error(e)
  } finally {
    confirming.value = false
  }
}

async function skip() {
  try {
    await api.post('/identity/confirm', { skip: true })
  } catch {}
  router.push('/')
}

function skillLabel(val) {
  if (val <= 20) return 'Elite'
  if (val <= 40) return 'Advanced'
  if (val <= 60) return 'Intermediate'
  if (val <= 80) return 'Recreational'
  return 'Beginner'
}

function skillBadgeClass(val) {
  if (val <= 20) return 'badge-success'
  if (val <= 40) return 'badge-info'
  if (val <= 60) return 'badge-warning'
  return 'badge-error'
}
</script>
