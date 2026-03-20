<template>
  <!-- DaisyUI modal -->
  <dialog ref="modalEl" class="modal modal-bottom sm:modal-middle" @close="$emit('close')">
    <div class="modal-box max-w-lg w-full">
      <!-- Header -->
      <div class="flex items-start justify-between mb-4">
        <div>
          <div class="text-xs text-base-content/50 uppercase tracking-wider mb-1">
            {{ game?.org?.name }} · {{ game?.division?.name }}
          </div>
          <div class="text-sm font-medium text-base-content/70">
            {{ formatDate(game?.scheduled_start) }}
          </div>
        </div>
        <button @click="close" class="btn btn-ghost btn-sm btn-circle">✕</button>
      </div>

      <!-- Lock countdown -->
      <div class="flex justify-center mb-5">
        <Countdown v-if="game?.lock_deadline" :deadline="game.lock_deadline" />
      </div>

      <!-- Teams comparison -->
      <div class="grid grid-cols-2 gap-4 mb-6">
        <!-- Home team -->
        <div
          class="card cursor-pointer transition-all duration-200 border-2"
          :class="selectedTeam === game?.home_team?.id
            ? 'border-primary bg-primary/10 shadow-lg shadow-primary/20'
            : 'border-base-content/10 bg-base-200 hover:border-primary/40'"
          @click="selectTeam(game?.home_team?.id)"
        >
          <div class="card-body p-4 text-center">
            <div class="text-xs text-base-content/50 mb-1">HOME</div>
            <div class="font-bold text-sm leading-tight mb-2">{{ game?.home_team?.name }}</div>
            <!-- Odds badge -->
            <div class="text-lg font-bold text-primary mb-2">{{ homeOdds }}×</div>
            <SkillBar :skill="game?.home_team?.avg_skill" />
            <div class="mt-2">
              <span v-if="isUnderdog(game?.home_team)" class="badge badge-warning badge-sm">underdog</span>
              <span v-else-if="isFavorite(game?.home_team)" class="badge badge-success badge-sm">favorite</span>
            </div>
          </div>
        </div>

        <!-- Away team -->
        <div
          class="card cursor-pointer transition-all duration-200 border-2"
          :class="selectedTeam === game?.away_team?.id
            ? 'border-secondary bg-secondary/10 shadow-lg shadow-secondary/20'
            : 'border-base-content/10 bg-base-200 hover:border-secondary/40'"
          @click="selectTeam(game?.away_team?.id)"
        >
          <div class="card-body p-4 text-center">
            <div class="text-xs text-base-content/50 mb-1">AWAY</div>
            <div class="font-bold text-sm leading-tight mb-2">{{ game?.away_team?.name }}</div>
            <!-- Odds badge -->
            <div class="text-lg font-bold text-secondary mb-2">{{ visitorOdds }}×</div>
            <SkillBar :skill="game?.away_team?.avg_skill" />
            <div class="mt-2">
              <span v-if="isUnderdog(game?.away_team)" class="badge badge-warning badge-sm">underdog</span>
              <span v-else-if="isFavorite(game?.away_team)" class="badge badge-success badge-sm">favorite</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Not logged in -->
      <template v-if="!isAuthenticated">
        <div class="alert alert-info mb-4">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span class="text-sm">Sign in to make picks and compete in leagues.</span>
        </div>
        <button @click="loginWithRedirect()" class="btn btn-primary w-full">
          Sign In to Pick
        </button>
      </template>

      <!-- Logged in: pick form -->
      <template v-else-if="isAuthenticated">
        <!-- Confidence selector -->
        <div class="mb-4">
          <div class="text-sm font-semibold mb-2 text-base-content/80">Confidence</div>
          <div class="grid grid-cols-3 gap-2">
            <button
              v-for="c in [1, 2, 3]"
              :key="c"
              @click="confidence = c"
              class="btn btn-sm"
              :class="confidence === c ? 'btn-primary' : 'btn-outline btn-primary'"
            >
              {{ c }}x
              <span class="text-xs opacity-70">
                {{ c === 1 ? 'safe' : c === 2 ? 'sure' : 'all-in' }}
              </span>
            </button>
          </div>
        </div>

        <!-- Wager input -->
        <div class="mb-4">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm font-semibold text-base-content/80">Wager</span>
            <span class="text-xs text-base-content/50">Balance: 💰 {{ balance.toLocaleString() }} pts</span>
          </div>
          <input
            v-model.number="wager"
            type="number"
            :min="10"
            :max="maxWager"
            :placeholder="`10–${maxWager} pts`"
            class="input input-bordered input-sm w-full"
            :disabled="!selectedTeam"
          />
          <div class="text-xs text-base-content/40 mt-1">Min 10 · Max {{ maxWager }} pts</div>
        </div>

        <!-- Projected P&L preview -->
        <div v-if="selectedTeam" class="rounded-xl border border-base-content/10 bg-base-200 px-4 py-3 mb-5 space-y-1">
          <div class="text-sm font-semibold text-base-content/70 mb-1">Projected P&amp;L</div>
          <div class="text-xs text-base-content/60">
            Effective stake: <span class="font-semibold text-base-content">{{ effectiveWager }} pts</span>
            ({{ wagerOrMin }} × {{ confidence }}x confidence)
          </div>
          <div class="text-xs text-success font-semibold">
            ✅ If correct: +{{ potentialPayout }} pts
            <span class="text-success/70 font-normal">(net +{{ potentialPayout - effectiveWager }} pts)</span>
          </div>
          <div class="text-xs text-error font-semibold">
            ❌ If wrong: −{{ effectiveWager }} pts
          </div>
        </div>

        <!-- Submit buttons -->
        <div class="grid grid-cols-2 gap-3">
          <button
            @click="submitPick(game?.home_team?.id)"
            class="btn btn-primary"
            :class="{ 'btn-outline': selectedTeam !== game?.home_team?.id }"
            :disabled="submitting || isGameLocked"
          >
            <span v-if="submitting && selectedTeam === game?.home_team?.id" class="loading loading-spinner loading-xs"></span>
            Pick Home · {{ homeOdds }}×
          </button>
          <button
            @click="submitPick(game?.away_team?.id)"
            class="btn btn-secondary"
            :class="{ 'btn-outline': selectedTeam !== game?.away_team?.id }"
            :disabled="submitting || isGameLocked"
          >
            <span v-if="submitting && selectedTeam === game?.away_team?.id" class="loading loading-spinner loading-xs"></span>
            Pick Away · {{ visitorOdds }}×
          </button>
        </div>

        <!-- Locked message -->
        <div v-if="isGameLocked" class="alert alert-error mt-4 text-sm">
          🔒 This game is locked — picks are closed.
        </div>

        <!-- Error message -->
        <div v-if="submitError" class="alert alert-error mt-4 text-sm">
          {{ submitError }}
        </div>

        <!-- Success message -->
        <div v-if="submitted" class="rounded-xl border border-success/40 bg-success/10 text-base-content mt-4 text-sm px-4 py-3">
          ✅ Pick saved! Good luck 🏒
        </div>
      </template>
    </div>

    <!-- Backdrop click to close -->
    <form method="dialog" class="modal-backdrop">
      <button @click="close">close</button>
    </form>
  </dialog>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useAuth0 } from '@auth0/auth0-vue'
import Countdown from './Countdown.vue'
import SkillBar from './SkillBar.vue'
import { usePicksStore } from '@/stores/picks'
import { useUserStore } from '@/stores/user'

const props = defineProps({
  game: {
    type: Object,
    default: null,
  },
  leagueId: {
    type: Number,
    default: null,
  },
  open: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['close', 'picked'])

const { isAuthenticated, loginWithRedirect } = useAuth0()
const picksStore = usePicksStore()
const userStore = useUserStore()

const modalEl = ref(null)
const selectedTeam = ref(null)
const confidence = ref(1)
const wager = ref(50)
const submitting = ref(false)
const submitted = ref(false)
const submitError = ref(null)

const balance = computed(() => userStore.balance)

// Odds from game data (computed by server from skill differential + vig)
const homeOdds = computed(() => props.game?.odds?.home_odds ?? 1.90)
const visitorOdds = computed(() => props.game?.odds?.visitor_odds ?? 1.90)

// Wager clamping
const maxWager = computed(() => {
  const bal = balance.value ?? 0
  return Math.max(10, Math.min(500, Math.floor(bal / 2)))
})

const wagerOrMin = computed(() => Math.max(10, Math.min(wager.value ?? 50, maxWager.value)))

const effectiveWager = computed(() => wagerOrMin.value * confidence.value)

const pickedOdds = computed(() => {
  if (!selectedTeam.value || !props.game) return 1.90
  return selectedTeam.value === props.game.home_team?.id ? homeOdds.value : visitorOdds.value
})

const potentialPayout = computed(() => Math.floor(effectiveWager.value * pickedOdds.value))

const isGameLocked = computed(() => {
  if (!props.game?.lock_deadline) return false
  return new Date(props.game.lock_deadline) <= new Date()
})

const isUpsetPick = computed(() => {
  if (!selectedTeam.value || !props.game) return false
  const picked = selectedTeam.value === props.game.home_team?.id
    ? props.game.home_team
    : props.game.away_team
  const opp = selectedTeam.value === props.game.home_team?.id
    ? props.game.away_team
    : props.game.home_team
  if (!picked?.avg_skill || !opp?.avg_skill) return false
  return picked.avg_skill > opp.avg_skill
})

function isUnderdog(team) {
  if (!team?.avg_skill || !props.game) return false
  const other = team.id === props.game.home_team?.id
    ? props.game.away_team
    : props.game.home_team
  return team.avg_skill > (other?.avg_skill ?? 50)
}

function isFavorite(team) {
  if (!team?.avg_skill || !props.game) return false
  const other = team.id === props.game.home_team?.id
    ? props.game.away_team
    : props.game.home_team
  return team.avg_skill < (other?.avg_skill ?? 50)
}

function selectTeam(teamId) {
  if (isGameLocked.value) return
  selectedTeam.value = teamId
  submitted.value = false
  submitError.value = null
}

function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
  })
}

async function submitPick(teamId) {
  if (!teamId || submitting.value || isGameLocked.value) return
  selectedTeam.value = teamId
  submitting.value = true
  submitError.value = null
  submitted.value = false
  try {
    const clampedWager = Math.max(10, Math.min(wager.value ?? 50, maxWager.value))
    const payload = {
      game_id: props.game.game_id,
      picked_team_id: teamId,
      confidence: confidence.value,
      wager: clampedWager,
    }
    if (props.leagueId) payload.league_id = props.leagueId
    console.log('[Pick] submitting payload:', JSON.stringify(payload))
    console.log('[Pick] game:', props.game?.game_id, 'home:', props.game?.home_team?.id, 'visitor:', props.game?.away_team?.id)
    const result = await picksStore.submitPick(payload)
    console.log('[Pick] success:', result)
    // Update balance from API response
    if (result?.balance !== undefined) {
      userStore.predUser = { ...userStore.predUser, balance: result.balance }
    }
    submitted.value = true
    emit('picked', { gameId: props.game.game_id, teamId, confidence: confidence.value })
  } catch (e) {
    console.error('[Pick] error:', e.response?.status, e.response?.data, e.message)
    submitError.value = e.response?.data?.message ?? 'Could not submit pick. Try again.'
  } finally {
    submitting.value = false
  }
}

function close() {
  selectedTeam.value = null
  confidence.value = 1
  wager.value = 50
  submitted.value = false
  submitError.value = null
  emit('close')
}

// Open/close the native dialog — pre-populate existing pick if any
watch(
  () => props.open,
  async (val) => {
    await nextTick()
    if (!modalEl.value) return
    if (val) {
      // Pre-fill from existing pick on the game
      const existing = props.game?.user_pick
      if (existing) {
        selectedTeam.value = existing.picked_team_id ?? null
        confidence.value = existing.confidence ?? 1
        wager.value = existing.wager ?? 50
      }
      modalEl.value.showModal()
    } else {
      modalEl.value.close()
    }
  }
)
</script>
