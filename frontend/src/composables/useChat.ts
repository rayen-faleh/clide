import { ref, readonly } from 'vue'
import type { WSMessage, ChatMessagePayload, ChatResponseChunkPayload } from '@/types/messages'

export interface ChatEntry {
  id: string
  content: string
  role: 'user' | 'assistant'
  timestamp: Date
  streaming?: boolean
}

export function useChat(sendWs: (msg: WSMessage) => void) {
  const messages = ref<ChatEntry[]>([])
  const isStreaming = ref(false)

  function sendMessage(content: string) {
    const userEntry: ChatEntry = {
      id: crypto.randomUUID(),
      content,
      role: 'user',
      timestamp: new Date(),
    }
    messages.value.push(userEntry)

    const wsMessage: WSMessage = {
      type: 'chat_message',
      payload: { content, role: 'user' } satisfies ChatMessagePayload,
      timestamp: new Date().toISOString(),
    }
    sendWs(wsMessage)

    // Create placeholder for assistant response
    const assistantEntry: ChatEntry = {
      id: crypto.randomUUID(),
      content: '',
      role: 'assistant',
      timestamp: new Date(),
      streaming: true,
    }
    messages.value.push(assistantEntry)
    isStreaming.value = true
  }

  function handleResponseChunk(msg: WSMessage) {
    const payload = msg.payload as unknown as ChatResponseChunkPayload
    if (payload.done) {
      // Mark streaming complete
      const lastAssistant = [...messages.value].reverse().find((m) => m.role === 'assistant')
      if (lastAssistant) {
        lastAssistant.streaming = false
      }
      isStreaming.value = false
      return
    }

    // Append chunk to last assistant message
    const lastAssistant = [...messages.value].reverse().find((m) => m.role === 'assistant')
    if (lastAssistant) {
      lastAssistant.content += payload.content
    }
  }

  function clearMessages() {
    messages.value = []
    isStreaming.value = false
  }

  return {
    messages: readonly(messages),
    isStreaming: readonly(isStreaming),
    sendMessage,
    handleResponseChunk,
    clearMessages,
  }
}
