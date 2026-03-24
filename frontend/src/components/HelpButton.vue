<template>
  <!-- DaisyUI modal -->
  <div class="modal" :class="{ 'modal-open': isOpen }">
    <div class="modal-box" style="max-width:480px;">
      <h3 class="font-bold text-lg mb-4">Help / Feedback</h3>

      <form @submit.prevent="submit">
        <!-- Title -->
        <div class="form-control mb-3">
          <label class="label"><span class="label-text">Title</span></label>
          <input
            v-model="form.title"
            type="text"
            class="input input-bordered w-full"
            placeholder="Brief summary of your issue or request"
            required
          />
        </div>

        <!-- Type -->
        <div class="form-control mb-3">
          <label class="label"><span class="label-text">Type</span></label>
          <select v-model="form.type" class="select select-bordered w-full">
            <option value="Bug">Bug</option>
            <option value="Feature Request">Feature Request</option>
            <option value="Question">Question</option>
          </select>
        </div>

        <!-- Description -->
        <div class="form-control mb-4">
          <label class="label"><span class="label-text">Description</span></label>
          <textarea
            v-model="form.description"
            class="textarea textarea-bordered w-full"
            placeholder="Please describe the issue or request in detail…"
            rows="4"
            required
          ></textarea>
        </div>

        <div class="modal-action mt-0">
          <button type="button" class="btn btn-ghost" @click="closeModal">Cancel</button>
          <button type="submit" class="btn btn-primary" :disabled="submitting">
            <span v-if="submitting" class="loading loading-spinner loading-sm"></span>
            <span v-else>Submit</span>
          </button>
        </div>
      </form>
    </div>
    <!-- Click outside to close -->
    <div class="modal-backdrop" @click="closeModal"></div>
  </div>

  <!-- Toast notification -->
  <div
    v-if="toast.visible"
    class="toast toast-end toast-bottom"
    style="z-index:10000;"
  >
    <div class="alert" :class="toast.type === 'success' ? 'alert-success' : 'alert-error'">
      <span>{{ toast.message }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'

const isOpen = ref(false)
const submitting = ref(false)

const form = reactive({
  title: '',
  type: 'Bug',
  description: '',
})

const toast = reactive({
  visible: false,
  type: 'success',
  message: '',
})

function openModal() {
  isOpen.value = true
}

function closeModal() {
  isOpen.value = false
}

function showToast(type, message) {
  toast.type = type
  toast.message = message
  toast.visible = true
  setTimeout(() => { toast.visible = false }, 4000)
}

async function submit() {
  submitting.value = true
  try {
    const res = await fetch('/api/support/issue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: form.title,
        type: form.type,
        description: form.description,
        page: window.location.pathname,
      }),
    })
    const data = await res.json()
    if (res.ok && data.ok) {
      showToast('success', '✅ Feedback submitted! Thank you.')
      closeModal()
      form.title = ''
      form.type = 'Bug'
      form.description = ''
    } else {
      showToast('error', '❌ Failed to submit: ' + (data.error || 'Unknown error'))
    }
  } catch (err) {
    showToast('error', '❌ Network error: ' + err.message)
  } finally {
    submitting.value = false
  }
}

defineExpose({ open: openModal })
</script>
