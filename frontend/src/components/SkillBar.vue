<template>
  <!--
    skill: 0 = elite (green), 100 = worst (red)
    We invert for display: fill% = 100 - skill
  -->
  <div class="flex items-center gap-2" :title="`Skill rating: ${skill ?? 'N/A'} (0=elite, 100=worst)`">
    <div class="flex-1 bg-base-300 rounded-full h-2 overflow-hidden min-w-[60px]">
      <div
        class="h-full rounded-full skill-bar-fill"
        :class="barColor"
        :style="{ width: fillPercent + '%' }"
      ></div>
    </div>
    <span class="text-xs font-mono w-6 text-right opacity-70">{{ displaySkill }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  skill: {
    type: Number,
    default: null,
  },
})

const fillPercent = computed(() => {
  if (props.skill === null || props.skill === undefined) return 50
  // Invert: skill 0 = 100% fill (elite), skill 100 = 0% fill (weak)
  return Math.max(0, Math.min(100, 100 - props.skill))
})

const displaySkill = computed(() => {
  if (props.skill === null || props.skill === undefined) return '?'
  return Math.round(props.skill)
})

// Color: green for elite (low skill value), red for weak (high skill value)
const barColor = computed(() => {
  const s = props.skill
  if (s === null || s === undefined) return 'bg-base-content/30'
  if (s < 30) return 'bg-success'
  if (s < 55) return 'bg-warning'
  return 'bg-error'
})
</script>
