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
            {{ game.org?.name ?? 'Unknown Org' }}<span v-if="game.division?.short_name" class="text-base-content/30 normal-case"> · {{ game.division.short_name }}</span>
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
          <a :href="'https://hockey-blast.com/team_stats?team_id=' + game.home_team?.id" target="_blank" class="link link-primary font-bold text-sm leading-tight mb-1" @click.stop>{{ game.home_team?.name ?? 'Home' }}</a>
          <div class="text-xs font-semibold text-primary/80 mb-1">{{ homeOdds }}×</div>
          <SkillBar :skill="game.home_team?.avg_skill" />
        </div>

        <!-- VS divider + matchup edge indicator -->
        <div class="text-center flex flex-col items-center gap-1">
          <span class="text-base-content/40 font-bold text-lg">vs</span>
          <span v-if="matchupLabel" class="text-xs px-1.5 py-0.5 rounded-full font-semibold" :class="matchupClass">{{ matchupLabel }}</span>
        </div>

        <!-- Away team -->
        <div class="text-center">
          <a :href="'https://hockey-blast.com/team_stats?team_id=' + game.visitor_team?.id" target="_blank" class="link link-primary font-bold text-sm leading-tight mb-1" @click.stop>{{ game.visitor_team?.name ?? 'Away' }}</a>
          <div class="text-xs font-semibold text-secondary/80 mb-1">{{ visitorOdds }}×</div>
          <SkillBar :skill="game.visitor_team?.avg_skill" />
        </div>
      </div>

      <!-- Footer: time + countdown + HB link -->
      <div class="flex items-center justify-between flex-wrap gap-2 pt-1 border-t border-base-content/5">
        <span class="text-xs text-base-content/50">
          {{ formatTime(game.scheduled_start) }}
        </span>
        <div class="flex items-center gap-2">
          <a v-if="game.game_id" :href="'https://hockey-blast.com/game_card?game_id=' + game.game_id" target="_blank" class="text-xs link link-secondary opacity-70" @click.stop>View on HB →</a>
          <Countdown v-if="game.lock_deadline" :deadline="game.lock_deadline" />
        </div>
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

const homeOdds = computed(() => props.game?.odds?.home_odds ?? 1.90)
const visitorOdds = computed(() => props.game?.odds?.visitor_odds ?? 1.90)

defineEmits(['pick'])

const isLocked = computed(
  () => props.game.lock_deadline && new Date(props.game.lock_deadline) <= new Date()
)

const matchupLabel = computed(() => {
  const h = props.game.home_team?.avg_skill
  const v = props.game.visitor_team?.avg_skill
  if (h == null || v == null) return null
  const diff = Math.abs(h - v)
  if (diff < 5) return '≈ Even'
  if (diff < 15) return h < v ? '← Edge' : 'Edge →'
  return h < v ? '← Favored' : 'Favored →'
})

const matchupClass = computed(() => {
  const h = props.game.home_team?.avg_skill
  const v = props.game.visitor_team?.avg_skill
  if (h == null || v == null) return ''
  const diff = Math.abs(h - v)
  if (diff < 5) return 'bg-base-300 text-base-content/60'
  if (diff < 15) return 'bg-warning/20 text-warning'
  return 'bg-primary/20 text-primary'
})

const pickedTeamName = computed(() => {
  if (!props.game.user_pick) return ''
  const pick = props.game.user_pick
  if (pick.picked_team_id === props.game.home_team?.id) return props.game.home_team?.name
  return props.game.visitor_team?.name
})

function formatTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  })
}
</script>
