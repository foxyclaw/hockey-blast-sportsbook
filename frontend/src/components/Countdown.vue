<template>
  <span :class="urgencyClass" class="font-mono text-sm font-semibold tabular-nums">
    <template v-if="locked">🔒 Locked</template>
    <template v-else>🕐 {{ timeLeft }}</template>
  </span>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  deadline: {
    type: String, // ISO8601
    required: true,
  },
})

const now = ref(Date.now())
let interval = null

onMounted(() => {
  interval = setInterval(() => {
    now.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  clearInterval(interval)
})

const diff = computed(() => new Date(props.deadline).getTime() - now.value)
const locked = computed(() => diff.value <= 0)

const timeLeft = computed(() => {
  const ms = diff.value
  if (ms <= 0) return 'Locked'
  const h = Math.floor(ms / 3600000)
  const m = Math.floor((ms % 3600000) / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
})

// Color urgency: >2h = success, 30m–2h = warning, <30m = error (pulsing)
const urgencyClass = computed(() => {
  const ms = diff.value
  if (locked.value) return 'text-base-content/40'
  if (ms > 2 * 3600000) return 'text-success'
  if (ms > 30 * 60000) return 'text-warning'
  return 'text-error lock-urgent'
})
</script>
