<template>
  <div class="modal modal-open">
    <div class="modal-box max-w-sm">
      <h3 class="font-bold text-base mb-1">What was wrong with this answer?</h3>
      <p class="text-sm text-base-content/60 mb-3">Optional — helps us improve</p>
      <textarea
        v-model="comment"
        class="textarea textarea-bordered w-full text-sm"
        placeholder="e.g. Wrong player, outdated stats, didn't understand the question..."
        rows="3"
        autofocus
      ></textarea>
      <div class="modal-action mt-3">
        <button class="btn btn-ghost btn-sm" @click="$emit('cancel')">Skip</button>
        <button class="btn btn-error btn-sm" @click="submit">Submit</button>
      </div>
    </div>
    <div class="modal-backdrop" @click="$emit('cancel')"></div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({ message: Object })
const emit = defineEmits(['submit', 'cancel'])
const comment = ref('')

function submit() {
  emit('submit', { comment: comment.value.trim() || null })
}
</script>
