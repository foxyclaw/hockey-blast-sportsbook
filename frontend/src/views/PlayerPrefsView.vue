<template>
  <div class="max-w-2xl mx-auto py-6 space-y-8">
    <!-- Header -->
    <div class="text-center">
      <h1 class="text-3xl font-bold">🏒 Player Profile</h1>
      <p class="text-base-content/60 mt-1">Tell us about your game so we can tailor your experience.</p>
    </div>

    <div v-if="loading" class="flex justify-center py-16">
      <span class="loading loading-spinner loading-lg text-primary"></span>
    </div>

    <template v-else>
      <!-- Section 0: Hockey Profile / Identity Linking -->
      <div class="card bg-base-200 shadow">
        <div class="card-body">
          <h2 class="card-title text-lg">🏒 Your Hockey Profile</h2>

          <!-- Loading claims -->
          <div v-if="claimsLoading" class="flex items-center gap-2 text-sm text-base-content/50">
            <span class="loading loading-spinner loading-xs"></span> Loading...
          </div>

          <template v-else>
            <!-- Existing claims -->
            <div v-if="existingClaims.length > 0" class="space-y-2 mb-3">
              <div
                v-for="claim in existingClaims"
                :key="claim.hb_human_id"
                class="flex items-start gap-3 rounded-xl border border-success/30 bg-success/10 p-3"
              >
                <span class="text-success mt-0.5">✅</span>
                <div class="flex-1 min-w-0">
                  <div class="font-semibold text-sm">
                    {{ claim.profile?.first_name }} {{ claim.profile?.last_name }}
                    <span v-if="claim.is_primary" class="badge badge-xs badge-success ml-1">Primary</span>
                  </div>
                  <div v-if="claim.profile?.orgs?.length" class="text-xs text-base-content/50 truncate">
                    {{ claim.profile.orgs.join(' · ') }}
                    <template v-if="claim.profile.first_date || claim.profile.last_date">
                      · {{ claim.profile.first_date }} – {{ claim.profile.last_date }}
                    </template>
                  </div>
                </div>
              </div>
            </div>

            <!-- No claims -->
            <p v-if="existingClaims.length === 0 && !showIdentitySearch" class="text-sm text-base-content/60 mb-3">
              Link your Hockey Blast player record to personalize your experience.
            </p>

            <!-- Add profile button -->
            <button
              v-if="!showIdentitySearch"
              class="btn btn-outline btn-sm w-fit"
              @click="openIdentitySearch"
            >
              {{ existingClaims.length === 0 ? '🔗 Find my hockey profile' : '+ Add another profile' }}
            </button>

            <!-- Inline search panel -->
            <div v-if="showIdentitySearch" class="mt-3 space-y-3">
              <div class="flex items-center justify-between">
                <span class="text-sm font-medium">Search for your player record</span>
                <button class="btn btn-ghost btn-xs" @click="showIdentitySearch = false">✕ Close</button>
              </div>

              <div v-if="candidatesLoading" class="flex items-center gap-2 text-sm text-base-content/50">
                <span class="loading loading-spinner loading-xs"></span> Searching...
              </div>

              <div v-else-if="identityCandidates.length === 0" class="text-sm text-base-content/50 italic">
                No matching player records found.
              </div>

              <div v-else class="space-y-2">
                <label
                  v-for="cand in identityCandidates"
                  :key="cand.hb_human_id"
                  class="cursor-pointer flex items-start gap-3 rounded-xl border-2 p-3 transition-all"
                  :class="selectedCandidateIds.includes(cand.hb_human_id)
                    ? 'border-primary bg-primary/10'
                    : 'border-base-300 bg-base-100'"
                >
                  <input
                    type="checkbox"
                    class="checkbox checkbox-primary checkbox-sm mt-0.5"
                    :value="cand.hb_human_id"
                    v-model="selectedCandidateIds"
                  />
                  <div class="flex-1 min-w-0">
                    <div class="font-semibold text-sm">
                      {{ cand.first_name }} {{ cand.last_name }}
                      <span v-if="cand.name_match" class="badge badge-xs badge-warning ml-1">Name Match</span>
                    </div>
                    <div v-if="cand.orgs?.length" class="text-xs text-base-content/50 truncate">{{ cand.orgs.join(' · ') }}</div>
                    <div v-if="cand.skill_value" class="text-xs text-base-content/40">Skill: {{ cand.skill_value }}</div>
                  </div>
                </label>
              </div>

              <div v-if="identityConfirmError" class="alert alert-error text-xs py-2">{{ identityConfirmError }}</div>

              <div class="flex gap-2">
                <button
                  class="btn btn-primary btn-sm"
                  :disabled="selectedCandidateIds.length === 0 || confirmingIdentity"
                  @click="confirmIdentity"
                >
                  <span v-if="confirmingIdentity" class="loading loading-spinner loading-xs"></span>
                  Confirm Selection
                </button>
                <button class="btn btn-ghost btn-sm" @click="skipIdentity">Skip</button>
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- Section 1: Skill Level -->
      <div class="card bg-base-200 shadow">
        <div class="card-body">
          <h2 class="card-title text-lg">⚡ Skill Level</h2>
          <p class="text-sm text-base-content/60 mb-3">How would you rate your hockey ability?</p>
          <div class="flex flex-wrap gap-3">
            <div
              v-for="level in skillLevels"
              :key="level.value"
              @click="form.skill_level = level.value"
              class="relative cursor-pointer rounded-xl border-2 p-3 flex flex-col items-center gap-1 w-28 transition-all select-none"
              :class="form.skill_level === level.value
                ? 'border-primary bg-primary/10'
                : 'border-base-300 bg-base-100 hover:border-primary/50'"
            >
              <span class="text-2xl">{{ level.emoji }}</span>
              <span class="font-semibold text-sm">{{ level.label }}</span>
              <span class="text-xs text-base-content/50 text-center leading-tight">{{ level.tagline }}</span>
              <div
                v-if="suggested_skill_level === level.value"
                class="absolute -top-2 -right-2 badge badge-xs badge-warning text-xs px-1"
              >💡 Suggested</div>
            </div>
          </div>
          <div class="form-control mt-4">
            <label class="label">
              <span class="label-text text-sm">Describe your level <span class="text-base-content/50">(optional)</span></span>
              <span class="label-text-alt text-xs text-base-content/40">{{ 500 - (form.skill_level_comment || '').length }} chars left</span>
            </label>
            <textarea
              v-model="form.skill_level_comment"
              class="textarea textarea-bordered bg-base-100 text-sm resize-none"
              rows="2"
              maxlength="500"
              placeholder="e.g. Played D3 college, now casual rec league on weekends"
            ></textarea>
          </div>
        </div>
      </div>

      <!-- Section 2: Locations -->
      <div class="card bg-base-200 shadow">
        <div class="card-body">
          <h2 class="card-title text-lg">📍 Where do you play?</h2>
          <p class="text-sm text-base-content/60 mb-3">Select all rinks / facilities you skate at.</p>
          <div v-if="locations.length === 0" class="text-sm text-base-content/40 italic">No locations available.</div>
          <div v-else class="space-y-4">
            <div v-for="group in locations" :key="group.state">
              <div class="text-xs font-bold text-base-content/50 uppercase tracking-wider mb-2">{{ group.state }}</div>
              <div class="flex flex-wrap gap-2">
                <span
                  v-for="loc in group.locations"
                  :key="loc.id"
                  @click="toggleLocation(loc.id)"
                  class="badge badge-lg cursor-pointer transition-all"
                  :class="form.interested_location_ids.includes(loc.id)
                    ? 'bg-primary text-primary-content border-primary'
                    : 'badge-outline'"
                >{{ loc.name }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Section 3: Availability -->
      <div class="card bg-base-200 shadow">
        <div class="card-body">
          <h2 class="card-title text-lg">📅 Availability</h2>
          <p class="text-sm text-base-content/60 mb-3">Let teams know you're available.</p>
          <div class="grid grid-cols-2 gap-3">
            <label
              class="cursor-pointer rounded-xl border-2 p-4 flex flex-col gap-2 transition-all"
              :class="form.is_free_agent ? 'border-primary bg-primary/10' : 'border-base-300 bg-base-100'"
            >
              <div class="flex items-center justify-between">
                <span class="font-semibold">🏒 Join a Team</span>
                <input type="checkbox" class="toggle toggle-primary toggle-sm" v-model="form.is_free_agent" />
              </div>
              <p class="text-xs text-base-content/50">I'm looking for a team to join.</p>
            </label>
            <label
              class="cursor-pointer rounded-xl border-2 p-4 flex flex-col gap-2 transition-all"
              :class="form.wants_to_sub ? 'border-primary bg-primary/10' : 'border-base-300 bg-base-100'"
            >
              <div class="flex items-center justify-between">
                <span class="font-semibold">📋 Sub Occasionally</span>
                <input type="checkbox" class="toggle toggle-primary toggle-sm" v-model="form.wants_to_sub" />
              </div>
              <p class="text-xs text-base-content/50">I'm open to subbing when teams need players.</p>
            </label>
          </div>
        </div>
      </div>

      <!-- Section 4: Captain Claims (only if there are candidates) -->
      <div v-if="captain_candidates.length > 0" class="card bg-base-200 shadow">
        <div class="card-body">
          <h2 class="card-title text-lg">🏆 Teams You Manage</h2>
          <p class="text-sm text-base-content/60 mb-3">We found teams where you've been captain. Confirm the ones that are yours.</p>
          <div class="space-y-2">
            <label
              v-for="team in captain_candidates"
              :key="team.team_id"
              class="cursor-pointer flex items-center gap-3 rounded-xl border-2 p-3 transition-all"
              :class="form.captain_team_ids.includes(team.team_id)
                ? 'border-primary bg-primary/10'
                : 'border-base-300 bg-base-100'"
            >
              <input
                type="checkbox"
                class="checkbox checkbox-primary"
                :value="team.team_id"
                v-model="form.captain_team_ids"
              />
              <div class="flex-1 min-w-0">
                <div class="font-semibold text-sm truncate">{{ team.team_name }}</div>
                <div v-if="team.org_name" class="text-xs text-base-content/50 truncate">{{ team.org_name }}</div>
              </div>
              <span v-if="team.already_claimed" class="badge badge-sm badge-success">Claimed</span>
            </label>
          </div>
        </div>
      </div>

      <!-- Section 5: Notifications -->
      <div class="card bg-base-200 shadow">
        <div class="card-body">
          <h2 class="card-title text-lg">🔔 Notifications</h2>
          <p class="text-sm text-base-content/60 mb-3">How should we reach you?</p>
          <div class="space-y-3">
            <label class="flex items-center justify-between rounded-xl border-2 p-3 cursor-pointer transition-all"
              :class="form.notify_email ? 'border-primary bg-primary/10' : 'border-base-300 bg-base-100'"
            >
              <div>
                <div class="font-semibold text-sm">📧 Email me</div>
                <div class="text-xs text-base-content/50">Game results, picks, league updates</div>
              </div>
              <input type="checkbox" class="toggle toggle-primary toggle-sm" v-model="form.notify_email" />
            </label>
            <label class="flex items-center justify-between rounded-xl border-2 p-3 cursor-pointer transition-all"
              :class="wantsPhone ? 'border-primary bg-primary/10' : 'border-base-300 bg-base-100'"
            >
              <div>
                <div class="font-semibold text-sm">📱 Text me</div>
                <div class="text-xs text-base-content/50">Time-sensitive alerts (game cancellations)</div>
              </div>
              <input type="checkbox" class="toggle toggle-primary toggle-sm" v-model="wantsPhone" />
            </label>
            <div v-if="wantsPhone" class="form-control">
              <input
                type="tel"
                placeholder="Phone number (e.g. 4155551234)"
                class="input input-bordered w-full"
                v-model="form.notify_phone"
                :class="phoneError ? 'input-error' : ''"
              />
              <div v-if="phoneError" class="label">
                <span class="label-text-alt text-error">{{ phoneError }}</span>
              </div>
            </div>
            <p class="text-xs text-base-content/40 italic">
              Standard messaging rates may apply. We'll never share your number.
            </p>
          </div>
        </div>
      </div>

      <!-- Error -->
      <div v-if="saveError" class="alert alert-error text-sm">
        <span>❌ {{ saveError }}</span>
      </div>

      <!-- Actions -->
      <div class="flex flex-col gap-3">
        <button
          class="btn btn-primary w-full"
          :disabled="saving"
          @click="save"
        >
          <span v-if="saving" class="loading loading-spinner loading-sm"></span>
          Save Profile
        </button>
        <button class="btn btn-ghost btn-sm w-full" @click="skip">
          Skip for now
        </button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApiClient } from '@/api/client'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const api = useApiClient()

const loading = ref(true)
const saving = ref(false)
const saveError = ref(null)
const wantsPhone = ref(false)

const suggested_skill_level = ref(null)
const captain_candidates = ref([])
const locations = ref([])

// Identity/hockey profile section
const existingClaims = ref([])
const claimsLoading = ref(true)
const showIdentitySearch = ref(false)
const identityCandidates = ref([])
const candidatesLoading = ref(false)
const selectedCandidateIds = ref([])
const confirmingIdentity = ref(false)
const identityConfirmError = ref(null)

const form = reactive({
  skill_level: null,
  skill_level_comment: '',
  is_free_agent: false,
  wants_to_sub: false,
  notify_email: true,
  notify_phone: '',
  interested_location_ids: [],
  captain_team_ids: [],
})

const skillLevels = [
  { value: 'elite',        emoji: '🌟', label: 'Elite',        tagline: 'Top of the league' },
  { value: 'advanced',     emoji: '⚡', label: 'Advanced',     tagline: 'Strong skater' },
  { value: 'intermediate', emoji: '🏒', label: 'Intermediate', tagline: 'Solid player' },
  { value: 'recreational', emoji: '🎿', label: 'Recreational', tagline: 'Playing for fun' },
  { value: 'beginner',     emoji: '🐣', label: 'Beginner',     tagline: 'Just starting out' },
]

const phoneError = computed(() => {
  if (!wantsPhone.value || !form.notify_phone) return null
  const digits = form.notify_phone.replace(/\D/g, '')
  if (digits.length < 10 || digits.length > 15) return 'Must be 10–15 digits'
  return null
})

function toggleLocation(id) {
  const idx = form.interested_location_ids.indexOf(id)
  if (idx === -1) form.interested_location_ids.push(id)
  else form.interested_location_ids.splice(idx, 1)
}

async function loadClaims() {
  claimsLoading.value = true
  try {
    const { data } = await api.get('/api/identity/my-claims')
    existingClaims.value = data.claims || []
  } catch (e) {
    console.error('[PlayerPrefs] failed to load identity claims', e)
    existingClaims.value = []
  } finally {
    claimsLoading.value = false
  }
}

async function openIdentitySearch() {
  showIdentitySearch.value = true
  selectedCandidateIds.value = []
  identityConfirmError.value = null
  if (identityCandidates.value.length === 0) {
    candidatesLoading.value = true
    try {
      const { data } = await api.get('/api/identity/candidates')
      identityCandidates.value = (data.candidates || []).slice(0, 5)
    } catch (e) {
      console.error('[PlayerPrefs] failed to load identity candidates', e)
      identityCandidates.value = []
    } finally {
      candidatesLoading.value = false
    }
  }
}

async function confirmIdentity() {
  if (selectedCandidateIds.value.length === 0) return
  confirmingIdentity.value = true
  identityConfirmError.value = null
  try {
    await api.post('/api/identity/confirm', { hb_human_id: selectedCandidateIds.value })
    showIdentitySearch.value = false
    identityCandidates.value = []
    await loadClaims()
  } catch (e) {
    identityConfirmError.value = e.response?.data?.message || 'Failed to confirm. Please try again.'
    console.error('[PlayerPrefs] identity confirm failed', e)
  } finally {
    confirmingIdentity.value = false
  }
}

async function skipIdentity() {
  showIdentitySearch.value = false
  try {
    await api.post('/api/identity/confirm', { skip: true })
  } catch (e) {
    // skip is best-effort
  }
}

onMounted(async () => {
  // Load identity claims in parallel
  loadClaims()

  try {
    const { data } = await api.get('/api/preferences')
    const prefs = data.preferences || {}

    form.skill_level = prefs.skill_level || null
    form.skill_level_comment = prefs.skill_level_comment || ''
    form.is_free_agent = prefs.is_free_agent || false
    form.wants_to_sub = prefs.wants_to_sub || false
    form.notify_email = prefs.notify_email !== false
    form.notify_phone = prefs.notify_phone || ''
    form.interested_location_ids = prefs.interested_location_ids || []

    suggested_skill_level.value = data.suggested_skill_level || null
    captain_candidates.value = data.captain_candidates || []
    locations.value = data.locations || []

    // Pre-fill captain claims from active ones
    const activeClaims = data.active_captain_claims || []
    form.captain_team_ids = activeClaims.map((c) => c.team_id)

    // Auto-select suggested skill if no saved pref
    if (!form.skill_level && suggested_skill_level.value) {
      form.skill_level = suggested_skill_level.value
    }

    // Determine phone toggle state
    wantsPhone.value = !!form.notify_phone
  } catch (e) {
    console.error('[PlayerPrefs] load failed', e)
  } finally {
    loading.value = false
  }
})

async function save() {
  if (phoneError.value) return

  saving.value = true
  saveError.value = null
  try {
    const payload = {
      skill_level: form.skill_level,
      skill_level_comment: form.skill_level_comment || '',
      is_free_agent: form.is_free_agent,
      wants_to_sub: form.wants_to_sub,
      notify_email: form.notify_email,
      notify_phone: wantsPhone.value ? form.notify_phone : '',
      interested_location_ids: form.interested_location_ids,
      captain_team_ids: form.captain_team_ids,
    }
    await api.patch('/api/preferences', payload)
    if (userStore.predUser) {
      userStore.predUser.preferences_completed = true
    }
    router.push('/')
  } catch (e) {
    const msg = e.response?.data?.message || e.message
    saveError.value = msg
    console.error('[PlayerPrefs] save failed', e)
  } finally {
    saving.value = false
  }
}

async function skip() {
  // Mark prefs as completed server-side and locally, then navigate away
  try {
    await api.patch('/api/preferences', {})
  } catch (e) {
    // best effort
  }
  if (userStore.predUser) {
    userStore.predUser.preferences_completed = true
  }
  router.replace({ name: 'home' })
}
</script>
