/**
 * Chat API — hockey stats AI queries with feedback.
 */
import { useApiClient } from '@/api/client'

export function useChatApi() {
  const api = useApiClient()

  return {
    async sendMessage(query, sessionId = null) {
      const { data } = await api.post('/api/chat/message', {
        query,
        session_id: sessionId,
      })
      return data
    },

    async submitFeedback(messageId, rating, comment = null) {
      const { data } = await api.post(`/api/chat/feedback/${messageId}`, {
        rating,
        comment,
      })
      return data
    },

    async getHistory() {
      const { data } = await api.get('/api/chat/history')
      return data.messages || []
    },
  }
}
