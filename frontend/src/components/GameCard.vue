<template>
  <div
    class="card bg-base-200 shadow-md hover:shadow-lg hover:shadow-primary/10 cursor-pointer transition-all duration-200 border border-base-content/5 hover:border-primary/30 active:scale-[0.99]"
    @click="$emit('pick', game)"
  >
    <div class="card-body p-4 gap-3">
      <!-- Header row: org/division + lock badge -->
      <div class="flex items-center justify-between flex-wrap gap-2">
        <div>
          <div class="text-xs text-base-content/50 uppercase tracking-wider">
            {{ game.org?.name ?? 'Unknown Org' }}
          </div>
          <div class="text-xs text-base-content/40">
            {{ game.division?.name ?? '' }}
          </div>
        </div>
        <div class="flex items-center gap-2">
          <span v-if="game.is_pickable && !isLocked" class="badge badge-success badge-sm">Pickable</span>
          <span v-else-if="isLocked" class="badge badge-error badge-sm">Locked</span>
          <span v-else class="badge badge-ghost badge-sm">Not pickable</span>
          <span v-if="game.is_live" class="badge badge-warning badge-sm animate-pulse">🔴 Live</span>
        </div>
      </div>

      <!-- Teams row -->
      <div class="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
        <!-- Home team -->
        <div class="text-center">
          <div class="font-bold text-sm leading-tight mb-2">{{ game.home_team?.name ?? 'Home' }}</div>
          <SkillBar :skill="game.home_team?.avg_skill" />
        </div>

        <!-- VS divider -->
        <div class="text-center">
          <span class="text-base-content/40 font-bold text-lg">vs</span>
        </div>

        <!-- Away team -->
        <div class="text-center">
          <div class="font-bold text-sm leading-tight mb-2">{{ game.away_team?.name ?? 'Away' }}</div>
          <SkillBar :skill="game.away_team?.avg_skill" />
        </div>
      </div>

      <!-- Footer: time + countdown -->
      <div class="flex items-center justify-between flex-wrap gap-2 pt-1 border-t border-base-content/5">
        <span class="text-xs text-base-content/50">
          {{ formatTime(game.scheduled_start) }}
        </span>
        <Countdown v-if="game.lock_deadline" :deadline="game.lock_deadline" />
      </div>

      <!-- Existing pick indicator -->
      <div v-if="game.user_pick" class="badge badge-primary badge-outline badge-sm self-start">
        ✓ Picked: {{ pickedTeamName }}
        <span class="ml-1 opacity-70">{{ game.user_pick.confidence }}x</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import SkillBar from './SkillBar.vue'
import Countdown from './Countdown.vue'

const props = defineProps({
  game: {
    type: Object,
    required: true,
  },
})

defineEmits(['pick'])

const isLocked = computed(
  () => props.game.lock_deadline && new Date(props.game.lock_deadline) <= new Date()
)

const pickedTeamName = computed(() => {
  if (!props.game.user_pick) return ''
  const pick = props.game.user_pick
  if (pick.picked_team_id === props.game.home_team?.id) return props.game.home_team?.name
  return props.game.away_team?.name
})

function formatTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  })
}
</script>
