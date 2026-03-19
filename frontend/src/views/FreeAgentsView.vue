<template>
  <div class="max-w-4xl mx-auto py-6 px-4 space-y-6">
    <!-- Header -->
    <div class="text-center">
      <h1 class="text-3xl font-bold">🏒 Free Agents &amp; Subs</h1>
      <p class="text-base-content/60 mt-1">Players looking for a team or available to sub.</p>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap gap-3 items-center justify-center">
      <select v-model="filterLevel" class="select select-sm select-bordered w-40">
        <option value="">All Levels</option>
        <option value="beginner">Beginner</option>
        <option value="intermediate">Intermediate</option>
        <option value="advanced">Advanced</option>
        <option value="elite">Elite</option>
      </select>

      <label class="label cursor-pointer gap-2">
        <span class="label-text text-sm">Subs only</span>
        <input type="checkbox" v-model="filterSubOnly" class="toggle toggle-sm toggle-primary" />
      </label>

      <div class="text-base-content/40 text-sm">
        {{ filteredAgents.length }} player{{ filteredAgents.length !== 1 ? 's' : '' }}
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-16">
      <span class="loading loading-spinner loading-lg text-primary"></span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="alert alert-error">
      <span>{{ error }}</span>
    </div>

    <!-- Empty state -->
    <div v-else-if="filteredAgents.length === 0" class="text-center py-16 text-base-content/40">
      <div class="text-4xl mb-3">🥅</div>
      <p class="text-lg">No players found</p>
      <p class="text-sm mt-1">Try adjusting the filters</p>
    </div>

    <!-- Player cards -->
    <div v-else class="grid gap-4 sm:grid-cols-2">
      <div
        v-for="player in filteredAgents"
        :key="player.user_id"
        class="card bg-base-200 shadow hover:shadow-md transition-shadow"
      >
        <div class="card-body p-4">
          <div class="flex items-start gap-3">
            <!-- Avatar -->
            <div class="avatar flex-shrink-0">
              <div class="w-12 h-12 rounded-full ring ring-primary/30 ring-offset-base-100 ring-offset-1">
                <img v-if="player.avatar_url" :src="player.avatar_url" :alt="player.display_name" />
                <div v-else class="bg-primary text-primary-content w-12 h-12 flex items-center justify-center rounded-full text-lg font-bold">
                  {{ player.display_name?.[0] ?? '?' }}
                </div>
              </div>
            </div>

            <!-- Info -->
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-semibold text-base">{{ player.display_name }}</span>
                <span v-if="player.skill_level" class="badge badge-outline badge-sm capitalize">
                  {{ player.skill_level }}
                </span>
              </div>

              <!-- HB Profile summary -->
              <div v-if="player.hb_profile" class="text-xs text-base-content/50 mt-0.5">
                <span v-if="player.hb_profile.orgs?.length">
                  {{ player.hb_profile.orgs.slice(0, 2).join(' · ') }}
                </span>
                <span v-if="player.hb_profile.first_date && player.hb_profile.last_date">
                  &nbsp;· Active {{ player.hb_profile.first_date?.slice(0, 4) }}–{{ player.hb_profile.last_date?.slice(0, 4) }}
                </span>
              </div>

              <!-- Tags -->
              <div class="flex gap-2 mt-2 flex-wrap">
                <span v-if="player.is_free_agent" class="text-xs text-success font-medium">✅ Free Agent</span>
                <span v-if="player.wants_to_sub" class="text-xs text-info font-medium">📋 Can Sub</span>
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="card-actions justify-end mt-3" v-if="isCaptain && isAuthenticated">
            <button
              class="btn btn-primary btn-xs"
              @click="openInviteModal(player)"
            >
              Invite to Team
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Invite Modal -->
    <div v-if="inviteModal.open" class="modal modal-open">
      <div class="modal-box">
        <h3 class="font-bold text-lg">Invite {{ inviteModal.player?.display_name }}</h3>
        <p class="text-sm text-base-content/60 mt-1">Send a roster invite to this player.</p>

        <div class="form-control mt-4">
          <label class="label"><span class="label-text">Team</span></label>
          <select v-model="inviteModal.teamId" class="select select-bordered">
            <option value="">Select a team</option>
            <option v-for="t in captainTeams" :key="t.hb_team_id" :value="t.hb_team_id">
              {{ t.team_name }}
            </option>
          </select>
        </div>

        <div class="form-control mt-3">
          <label class="label"><span class="label-text">Message (optional)</span></label>
          <textarea
            v-model="inviteModal.message"
            class="textarea textarea-bordered"
            placeholder="Hey, we'd love to have you on the team!"
            rows="3"
          ></textarea>
        </div>

        <div v-if="inviteModal.error" class="alert alert-error mt-3 text-sm py-2">
          {{ inviteModal.error }}
        </div>

        <div class="modal-action">
          <button class="btn btn-ghost btn-sm" @click="inviteModal.open = false">Cancel</button>
          <button
            class="btn btn-primary btn-sm"
            :disabled="!inviteModal.teamId || inviteModal.sending"
            @click="sendInvite"
          >
            <span v-if="inviteModal.sending" class="loading loading-spinner loading-xs"></span>
            Send Invite
          </button>
        </div>
      </div>
      <div class="modal-backdrop" @click="inviteModal.open = false"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuth0 } from '@auth0/auth0-vue'
import { useApiClient } from '@/api/client'
import { useUserStore } from '@/stores/user'

const { isAuthenticated } = useAuth0()
const userStore = useUserStore()

const agents = ref([])
const loading = ref(false)
const error = ref(null)
const filterLevel = ref('')
const filterSubOnly = ref(false)

const inviteModal = ref({
  open: false,
  player: null,
  teamId: '',
  message: '',
  error: null,
  sending: false,
})

// Check if current user is a captain
const isCaptain = computed(() => {
  return isAuthenticated.value && (userStore.captainClaims?.length > 0)
})

const captainTeams = computed(() => {
  return userStore.captainClaims || []
})

const filteredAgents = computed(() => {
  let list = agents.value
  if (filterLevel.value) {
    list = list.filter(p => p.skill_level === filterLevel.value)
  }
  if (filterSubOnly.value) {
    list = list.filter(p => p.wants_to_sub)
  }
  return list
})

async function loadAgents() {
  loading.value = true
  error.value = null
  try {
    const api = useApiClient()
    const { data } = await api.get('/api/free-agents')
    agents.value = data.free_agents || []
  } catch (e) {
    error.value = 'Failed to load free agents. Please try again.'
    console.error('[FreeAgents] load error', e)
  } finally {
    loading.value = false
  }
}

function openInviteModal(player) {
  inviteModal.value = {
    open: true,
    player,
    teamId: captainTeams.value[0]?.hb_team_id || '',
    message: '',
    error: null,
    sending: false,
  }
}

async function sendInvite() {
  const modal = inviteModal.value
  if (!modal.teamId) return

  const team = captainTeams.value.find(t => t.hb_team_id === modal.teamId || t.hb_team_id == modal.teamId)
  modal.sending = true
  modal.error = null

  try {
    const api = useApiClient()
    await api.post('/api/roster-invites', {
      to_user_id: modal.player.user_id,
      hb_team_id: modal.teamId,
      team_name: team?.team_name || 'My Team',
      message: modal.message || null,
    })
    inviteModal.value.open = false
  } catch (e) {
    const msg = e.response?.data?.message || 'Failed to send invite'
    modal.error = msg
  } finally {
    modal.sending = false
  }
}

onMounted(() => {
  loadAgents()
})
</script>
