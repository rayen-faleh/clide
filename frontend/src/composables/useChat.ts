import { readonly } from 'vue'
import { storeToRefs } from 'pinia'
import { useAgentStore } from '@/stores/agent'
import type { WSMessage, ChatMessagePayload, ChatResponseChunkPayload } from '@/types/messages'

export type { ChatEntry } from '@/stores/agent'

export function useChat(sendWs: (msg: WSMessage) => void) {
  const store = useAgentStore()
  const { messages, isStreaming } = storeToRefs(store)

  function sendMessage(content: string) {
    store.addMessage({
      id: crypto.randomUUID(),
      content,
      role: 'user',
      timestamp: new Date(),
    })

    const wsMessage: WSMessage = {
      type: 'chat_message',
      payload: { content, role: 'user' } satisfies ChatMessagePayload,
      timestamp: new Date().toISOString(),
    }
    sendWs(wsMessage)

    // Create placeholder for assistant response
    store.addMessage({
      id: crypto.randomUUID(),
      content: '',
      role: 'assistant',
      timestamp: new Date(),
      streaming: true,
    })
    store.isStreaming = true
  }

  function handleResponseChunk(msg: WSMessage) {
    const payload = msg.payload as unknown as ChatResponseChunkPayload
    store.updateLastAssistant(payload.content, payload.done)
  }

  function clearMessages() {
    store.clearMessages()
  }

  return {
    messages: readonly(messages),
    isStreaming: readonly(isStreaming),
    sendMessage,
    handleResponseChunk,
    clearMessages,
  }
}
