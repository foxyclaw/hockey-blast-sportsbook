<template>
  <div class="max-w-2xl mx-auto py-6 space-y-6">
    <!-- Header -->
    <div class="text-center">
      <h1 class="text-3xl font-bold">🏒 My Identity</h1>
      <p class="text-base-content/60 mt-1">Manage your linked Hockey Blast player profiles.</p>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-16">
      <span class="loading loading-spinner loading-lg text-primary"></span>
    </div>

    <template v-else>
      <!-- Linked claims -->
      <div class="card bg-base-200 shadow">
        <div class="card-body">
          <h2 class="card-title text-lg">🔗 Linked Profiles</h2>

          <div v-if="claims.length === 0" class="text-sm text-base-content/50 italic py-2">
            No linked profiles yet. Go to your
            <router-link to="/player-prefs" class="link link-primary">player settings</router-link>
            to add one.
          </div>

          <div v-else class="space-y-3">
            <div
              v-for="claim in claims"
              :key="claim.hb_human_id"
              class="flex items-start gap-3 rounded-xl border p-4 transition-all"
              :class="claim.is_primary
                ? 'border-primary/40 bg-primary/5'
                : 'border-base-300 bg-base-100'"
            >
              <!-- Status icon -->
              <span class="mt-0.5 text-lg">
                <span v-if="claim.is_primary">⭐</span>
                <span v-else-if="claim.claim_status === 'confirmed'">✅</span>
                <span v-else-if="claim.claim_status === 'pending_review'">⏳</span>
                <span v-else>❓</span>
              </span>

              <!-- Profile info -->
              <div class="flex-1 min-w-0">
                <div class="font-semibold">
                  {{ claim.profile?.first_name }}{{ claim.profile?.middle_name ? ' ' + claim.profile.middle_name : '' }} {{ claim.profile?.last_name }}
                </div>
                <div class="flex flex-wrap gap-1 mt-1">
                  <span v-if="claim.is_primary" class="badge badge-xs badge-primary">Primary</span>
                  <span v-if="claim.claim_status === 'pending_review'" class="badge badge-xs badge-warning">Pending Review</span>
                  <span v-if="claim.claim_status === 'confirmed' && !claim.is_primary" class="badge badge-xs badge-success">Confirmed</span>
                </div>
                <div v-if="claim.profile?.orgs?.length" class="text-xs text-base-content/50 mt-1 truncate">
                  {{ claim.profile.orgs.join(' · ') }}
                  <template v-if="claim.profile.first_date || claim.profile.last_date">
                    · {{ claim.profile.first_date }} – {{ claim.profile.last_date }}
                  </template>
                </div>
                <div v-if="claim.profile?.skill_value" class="text-xs text-base-content/40 mt-0.5">
                  Skill: {{ claim.profile.skill_value }}
                </div>
              </div>

            </div>
          </div>

          <!-- Add another profile -->
          <div class="mt-4">
            <router-link to="/player-prefs" class="btn btn-outline btn-sm">
              + Add another profile
            </router-link>
          </div>
        </div>
      </div>

      <!-- Info box -->
      <div class="rounded-xl bg-base-200 border border-base-300 p-4 text-sm text-base-content/70 space-y-1">
        <p>⭐ <strong>Primary</strong> is your main identity — used for stats, picks, and leaderboard display.</p>
        <p>🔗 Linked profiles are merged so your full career history is tracked together.</p>
        <p>⏳ Claims marked <strong>Pending Review</strong> are awaiting admin approval (another user has claimed the same record).</p>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useApiClient } from '@/api/client'

const api = useApiClient()

const loading = ref(true)
const claims = ref([])

async function loadClaims() {
  try {
    const { data } = await api.get('/api/identity/my-claims')
    claims.value = data.claims || []
  } catch (e) {
    console.error('[IdentityView] failed to load claims', e)
    claims.value = []
  }
}

onMounted(async () => {
  await loadClaims()
  loading.value = false
})
</script>
