<template>
  <div class="container mx-auto px-4 py-12 max-w-md">
    <div class="card bg-base-200 shadow-xl p-8">
      <h1 class="text-2xl font-bold text-primary mb-2">👋 Welcome!</h1>
      <p class="text-base-content/60 text-sm mb-6">
        We just need your name to get started. This is how you'll appear in leagues and standings.
      </p>

      <div class="space-y-4">
        <div class="form-control">
          <label class="label"><span class="label-text">First name</span></label>
          <input
            v-model="firstName"
            type="text"
            placeholder="Pavel"
            class="input input-bordered w-full"
            @keyup.enter="focusLast"
            ref="firstRef"
            autocomplete="given-name"
            autofocus
          />
        </div>
        <div class="form-control">
          <label class="label"><span class="label-text">Last name</span></label>
          <input
            v-model="lastName"
            type="text"
            placeholder="Kletskov"
            class="input input-bordered w-full"
            @keyup.enter="submit"
            ref="lastRef"
            autocomplete="family-name"
          />
        </div>

        <div v-if="error" class="alert alert-error text-sm">{{ error }}</div>

        <button
          class="btn btn-primary w-full mt-2"
          :class="{ loading: saving }"
          :disabled="saving || !firstName.trim() || !lastName.trim()"
          @click="submit"
        >
          Continue
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useApiClient } from '@/api/client'
import { useUserStore } from '@/stores/user'

const api = useApiClient()
const router = useRouter()
const userStore = useUserStore()

const firstName = ref('')
const lastName = ref('')
const saving = ref(false)
const error = ref('')
const firstRef = ref(null)
const lastRef = ref(null)

function focusLast() {
  lastRef.value?.focus()
}

async function submit() {
  if (!firstName.value.trim() || !lastName.value.trim()) return
  saving.value = true
  error.value = ''
  try {
    const displayName = `${firstName.value.trim()} ${lastName.value.trim()}`
    await api.patch('/auth/me', { display_name: displayName })
    // Refresh the store so needsIdentitySetup recalculates
    await userStore.fetchPredUser(null)
    router.push({ name: 'player-prefs' })
  } catch (e) {
    error.value = 'Something went wrong, please try again.'
    console.error(e)
  } finally {
    saving.value = false
  }
}
</script>
