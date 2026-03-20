<template>
  <div class="text-xs text-base-content/60" :title="`Skill rating: ${skill ?? 'N/A'} — lower = stronger`">
    <span v-if="skill !== null && skill !== undefined">Skill: {{ Math.round(skill) === 0 ? 'N/A' : Math.round(skill) }}</span>
  </div>
</template>

<script setup>
defineProps({
  skill: {
    type: Number,
    default: null,
  },
})
</script>
