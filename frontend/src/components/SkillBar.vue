<template>
  <div class="flex items-center gap-1.5" :title="`Skill: ${skill ?? 'N/A'} — lower = stronger team`">
    <div class="flex-1 bg-base-300 rounded-full h-2.5 overflow-hidden w-full">
      <div
        class="h-full rounded-full transition-all duration-300"
        :class="barColor"
        :style="{ width: fillPercent + '%' }"
      ></div>
    </div>
    <span class="text-xs font-bold w-7 text-right" :class="labelColor">{{ displaySkill }}</span>
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
  return Math.max(5, Math.min(100, 100 - props.skill))
})

const displaySkill = computed(() => {
  if (props.skill === null || props.skill === undefined) return '?'
  return Math.round(props.skill)
})

const barColor = computed(() => {
  const s = props.skill
  if (s === null || s === undefined) return 'bg-base-content/30'
  if (s < 30) return 'bg-success'
  if (s < 55) return 'bg-warning'
  return 'bg-error'
})

const labelColor = computed(() => {
  const s = props.skill
  if (s === null || s === undefined) return 'text-base-content/50'
  if (s < 30) return 'text-success'
  if (s < 55) return 'text-warning'
  return 'text-error'
})
</script>
