<template>
  <!-- Floating chat button + panel -->
  <div class="chat-root">
    <!-- Toggle button -->
    <button
      class="btn btn-circle btn-lg chat-fab shadow-xl"
      :class="open ? 'btn-error' : 'btn-primary'"
      @click="isLoggedIn ? (open = !open) : (open = true)"
      title="AI Blast"
    >
      <span v-if="!open">🏒</span>
      <span v-else class="text-xl font-bold">✕</span>
    </button>

    <!-- Chat panel -->
    <Transition name="chat-slide">
      <div v-if="open" class="chat-panel card bg-base-200 shadow-2xl" :class="{ maximized: maximized }">
        <!-- Header -->
        <div class="chat-header bg-primary text-primary-content px-4 py-3 rounded-t-2xl flex items-center gap-2">
          <span class="text-lg">🏒</span>
          <div class="flex-1">
            <div class="font-bold text-sm">AI Blast</div>
            <div class="text-xs opacity-75">Ask anything about players, teams & games</div>
          </div>
          <button
            @click="maximized = !maximized"
            class="btn btn-ghost btn-xs btn-circle text-primary-content opacity-80 hover:opacity-100"
            :title="maximized ? 'Minimize' : 'Maximize'"
          >
            <span v-if="maximized">⊙</span>
            <span v-else>⛶</span>
          </button>
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
              <div class="chat-bubble bg-base-100 text-base-content text-sm" v-html="renderMarkdown(msg.answer)"></div>
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
          <div v-if="!isLoggedIn" class="text-center py-2">
            <p class="text-xs text-base-content/60 mb-2">Sign in to chat with the AI Blast assistant 🏒</p>
            <button @click="loginWithRedirect()" class="btn btn-primary btn-sm">Sign In</button>
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
import { ref, nextTick, computed, watch } from 'vue'
import { useAuth0 } from '@auth0/auth0-vue'
import { useChatApi } from '@/api/chat'
import DislikeModal from '@/components/DislikeModal.vue'

const { isAuthenticated, loginWithRedirect } = useAuth0()
const isLoggedIn = computed(() => isAuthenticated.value)

const chatApi = useChatApi()
const open = ref(false)
const maximized = ref(false)
const input = ref('')
const loading = ref(false)
const messages = ref([])
const messagesEl = ref(null)
const inputEl = ref(null)
const dislikeTarget = ref(null)

const sessionId = crypto.randomUUID()
const historyLoaded = ref(false)

// Load history the first time the chat is opened
watch(open, async (isOpen) => {
  if (!isOpen || historyLoaded.value) return
  historyLoaded.value = true
  try {
    const history = await chatApi.getHistory()
    if (history?.length) {
      // Map history format to local message format
      messages.value = history.map(m => ({
        id: m.id,
        message_id: m.id,
        query: m.query,
        answer: m.answer,
        tools_used: m.tools_used || [],
        feedback: null,
        is_off_topic: m.is_off_topic || false,
      }))
      await nextTick()
      await scrollToBottom()
    }
  } catch (e) {
    console.warn('[Chat] history load failed:', e)
  }
})

const hints = [
  "Best game by Pavel Kletskov?",
  "Who scored most goals ever?",
  "Top penalty leaders?",
  "Biggest rivalry?",
]

function renderMarkdown(text) {
  if (!text) return ''
  return text
    // Headers
    .replace(/^### (.+)$/gm, '<div class="font-bold text-base mt-3 mb-1">$1</div>')
    .replace(/^## (.+)$/gm, '<div class="font-bold text-lg mt-3 mb-1">$1</div>')
    .replace(/^# (.+)$/gm, '<div class="font-bold text-xl mt-3 mb-1">$1</div>')
    // Bold + italic
    .replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    // Horizontal rule
    .replace(/^---+$/gm, '<hr class="border-base-content/20 my-2">')
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="bg-base-300 px-1 rounded text-xs">$1</code>')
    // Tables — wrap in overflow div
    .replace(/((\|.+\|\n?)+)/g, (match) => {
      const rows = match.trim().split('\n')
      let html = '<div class="overflow-x-auto my-2"><table class="table table-xs w-full text-xs">'
      rows.forEach((row, i) => {
        if (/^\|[-| ]+\|$/.test(row.trim())) return // separator row
        const cells = row.split('|').filter((_, idx, arr) => idx > 0 && idx < arr.length - 1)
        const tag = i === 0 ? 'th' : 'td'
        html += '<tr>' + cells.map(c => `<${tag} class="border border-base-content/10 px-2 py-1">${c.trim()}</${tag}>`).join('') + '</tr>'
      })
      html += '</table></div>'
      return html
    })
    // Line breaks (after block elements handled above)
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
  right: max(24px, calc((100vw - 72rem) / 2));
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
  transition: width 0.2s ease, height 0.2s ease, bottom 0.2s ease, right 0.2s ease, border-radius 0.2s ease;
}
.chat-panel.maximized {
  position: fixed;
  bottom: 80px;
  right: max(24px, calc((100vw - 72rem) / 2));
  width: min(860px, calc(100vw - 48px));
  height: calc(100vh - 180px);
  border-radius: 1rem;
}

/* Mobile maximized — true fullscreen */
@media (max-width: 640px) {
  .chat-panel.maximized {
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    width: 100vw;
    height: 100dvh;
    border-radius: 0;
  }
}
.chat-messages {
  scrollbar-width: thin;
}
/* Mobile: fullscreen panel + prevent iOS auto-zoom on input focus */
@media (max-width: 640px) {
  .chat-panel {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    width: 100vw;
    height: 100dvh;
    border-radius: 0;
  }
  .chat-panel input, .chat-panel textarea {
    font-size: 16px !important;
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
