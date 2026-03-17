<template>
  <!-- Floating chat button + panel -->
  <div class="chat-root">
    <!-- Toggle button -->
    <button
      class="btn btn-circle btn-lg chat-fab shadow-xl"
      :class="open ? 'btn-error' : 'btn-primary'"
      @click="open = !open"
      title="Hockey Stats AI"
    >
      <span v-if="!open">🏒</span>
      <span v-else class="text-xl font-bold">✕</span>
    </button>

    <!-- Chat panel -->
    <Transition name="chat-slide">
      <div v-if="open" class="chat-panel card bg-base-200 shadow-2xl">
        <!-- Header -->
        <div class="chat-header bg-primary text-primary-content px-4 py-3 rounded-t-2xl flex items-center gap-2">
          <span class="text-lg">🏒</span>
          <div>
            <div class="font-bold text-sm">Hockey Stats AI</div>
            <div class="text-xs opacity-75">Ask anything about players, teams & games</div>
          </div>
        </div>

        <!-- Messages -->
        <div class="chat-messages flex-1 overflow-y-auto p-3 flex flex-col gap-3" ref="messagesEl">
          <!-- Welcome -->
          <div v-if="messages.length === 0" class="text-center text-base-content/50 text-sm mt-8">
            <div class="text-3xl mb-2">🏒</div>
            <div>Ask me about players, teams, scores, records...</div>
            <div class="mt-3 flex flex-wrap gap-2 justify-center">
              <button
                v-for="hint in hints"
                :key="hint"
                class="badge badge-outline badge-sm cursor-pointer hover:badge-primary"
                @click="askHint(hint)"
              >{{ hint }}</button>
            </div>
          </div>

          <!-- Message bubbles -->
          <div v-for="msg in messages" :key="msg.id" class="flex flex-col gap-1">
            <!-- User bubble -->
            <div class="chat chat-end">
              <div class="chat-bubble chat-bubble-primary text-sm">{{ msg.query }}</div>
            </div>
            <!-- Assistant bubble -->
            <div class="chat chat-start">
              <div class="chat-bubble bg-base-100 text-base-content text-sm whitespace-pre-wrap" v-html="renderMarkdown(msg.answer)"></div>
              <!-- Tools used (collapsible) -->
              <div v-if="msg.tools_used?.length" class="mt-1 ml-1">
                <details class="text-xs text-base-content/40">
                  <summary class="cursor-pointer hover:text-base-content/60">
                    🔧 {{ msg.tools_used.length }} tool{{ msg.tools_used.length > 1 ? 's' : '' }} used
                  </summary>
                  <div class="mt-1 flex flex-wrap gap-1">
                    <span v-for="t in msg.tools_used" :key="t" class="badge badge-ghost badge-xs">{{ t }}</span>
                  </div>
                </details>
              </div>
              <!-- Feedback buttons -->
              <div v-if="!msg.is_off_topic" class="flex gap-2 mt-1 ml-1">
                <button
                  class="btn btn-ghost btn-xs"
                  :class="msg.feedback === 'like' ? 'text-success' : 'text-base-content/30'"
                  @click="giveFeedback(msg, 'like')"
                  title="Good answer"
                >👍</button>
                <button
                  class="btn btn-ghost btn-xs"
                  :class="msg.feedback === 'dislike' ? 'text-error' : 'text-base-content/30'"
                  @click="openDislike(msg)"
                  title="Bad answer"
                >👎</button>
              </div>
            </div>
          </div>

          <!-- Loading indicator -->
          <div v-if="loading" class="chat chat-start">
            <div class="chat-bubble bg-base-100">
              <span class="loading loading-dots loading-sm"></span>
            </div>
          </div>
        </div>

        <!-- Input -->
        <div class="p-3 border-t border-base-300">
          <form @submit.prevent="send" class="flex gap-2">
            <input
              v-model="input"
              type="text"
              placeholder="Ask about hockey stats..."
              class="input input-bordered input-sm flex-1 text-sm"
              :disabled="loading || !isLoggedIn"
              ref="inputEl"
            />
            <button
              type="submit"
              class="btn btn-primary btn-sm"
              :disabled="loading || !input.trim() || !isLoggedIn"
            >Send</button>
          </form>
          <div v-if="!isLoggedIn" class="text-xs text-base-content/50 mt-1 text-center">
            Log in to use the chat
          </div>
        </div>
      </div>
    </Transition>

    <!-- Dislike comment modal -->
    <DislikeModal
      v-if="dislikeTarget"
      :message="dislikeTarget"
      @submit="onDislikeSubmit"
      @cancel="dislikeTarget = null"
    />
  </div>
</template>

<script setup>
import { ref, nextTick, computed } from 'vue'
import { useAuth0 } from '@auth0/auth0-vue'
import { useChatApi } from '@/api/chat'
import DislikeModal from '@/components/DislikeModal.vue'

const { isAuthenticated } = useAuth0()
const isLoggedIn = computed(() => isAuthenticated.value)

const chatApi = useChatApi()
const open = ref(false)
const input = ref('')
const loading = ref(false)
const messages = ref([])
const messagesEl = ref(null)
const inputEl = ref(null)
const dislikeTarget = ref(null)

const sessionId = crypto.randomUUID()

const hints = [
  "Best game by Pavel Kletskov?",
  "Who scored most goals ever?",
  "Top penalty leaders?",
  "Biggest rivalry?",
]

function renderMarkdown(text) {
  if (!text) return ''
  // Simple: bold **text**, line breaks, preserve tables
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
}

async function send() {
  const q = input.value.trim()
  if (!q || loading.value) return
  input.value = ''
  loading.value = true

  // Optimistic: show query immediately
  const tempId = Date.now()
  messages.value.push({ id: tempId, query: q, answer: null, tools_used: [], feedback: null, is_off_topic: false })
  await scrollToBottom()

  try {
    const result = await chatApi.sendMessage(q, sessionId)
    // Replace the temp message with the real one
    const idx = messages.value.findIndex(m => m.id === tempId)
    if (idx !== -1) messages.value[idx] = { ...result, query: q, feedback: null }
  } catch (err) {
    const idx = messages.value.findIndex(m => m.id === tempId)
    if (idx !== -1) messages.value[idx].answer = `Error: ${err.response?.data?.message || err.message}`
  } finally {
    loading.value = false
    await scrollToBottom()
    nextTick(() => inputEl.value?.focus())
  }
}

function askHint(hint) {
  input.value = hint
  send()
}

async function giveFeedback(msg, rating) {
  if (!msg.message_id) return
  msg.feedback = rating
  await chatApi.submitFeedback(msg.message_id, rating)
}

function openDislike(msg) {
  dislikeTarget.value = msg
}

async function onDislikeSubmit({ comment }) {
  if (!dislikeTarget.value) return
  const msg = dislikeTarget.value
  msg.feedback = 'dislike'
  await chatApi.submitFeedback(msg.message_id, 'dislike', comment)
  dislikeTarget.value = null
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}
</script>

<style scoped>
.chat-root {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 9999;
}
.chat-fab {
  width: 56px;
  height: 56px;
  font-size: 1.4rem;
}
.chat-panel {
  position: absolute;
  bottom: 70px;
  right: 0;
  width: 360px;
  height: 520px;
  display: flex;
  flex-direction: column;
  border-radius: 1rem;
  overflow: hidden;
}
.chat-messages {
  scrollbar-width: thin;
}
/* Mobile: full width */
@media (max-width: 400px) {
  .chat-panel {
    width: calc(100vw - 16px);
    right: -8px;
  }
}
.chat-slide-enter-active, .chat-slide-leave-active {
  transition: all 0.2s ease;
}
.chat-slide-enter-from, .chat-slide-leave-to {
  opacity: 0;
  transform: translateY(16px) scale(0.97);
}
</style>
