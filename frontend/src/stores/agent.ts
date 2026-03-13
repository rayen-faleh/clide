import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AgentState, MoodPayload, WSMessage } from '@/types/messages'

export interface ChatEntry {
  id: string
  content: string
  role: 'user' | 'assistant'
  timestamp: Date
  streaming?: boolean
}

export const useAgentStore = defineStore('agent', () => {
  const state = ref<AgentState>('idle')
  const mood = ref<MoodPayload | null>(null)
  const currentThought = ref<string | null>(null)
  const connected = ref(false)

  // Chat state — persists across navigation
  const messages = ref<ChatEntry[]>([])
  const isStreaming = ref(false)

  function handleStateChange(msg: WSMessage) {
    const payload = msg.payload as { new_state: AgentState }
    state.value = payload.new_state
  }

  function handleMoodUpdate(msg: WSMessage) {
    mood.value = msg.payload as unknown as MoodPayload
  }

  function handleThought(msg: WSMessage) {
    const payload = msg.payload as { content: string }
    currentThought.value = payload.content
  }

  function setConnected(value: boolean) {
    connected.value = value
  }

  function addMessage(entry: ChatEntry) {
    messages.value.push(entry)
  }

  function updateLastAssistant(content: string, done: boolean) {
    const lastAssistant = [...messages.value].reverse().find((m) => m.role === 'assistant')
    if (lastAssistant) {
      if (done) {
        lastAssistant.streaming = false
      } else {
        lastAssistant.content += content
      }
    }
    if (done) {
      isStreaming.value = false
    }
  }

  function clearMessages() {
    messages.value = []
    isStreaming.value = false
  }

  return {
    state,
    mood,
    currentThought,
    connected,
    messages,
    isStreaming,
    handleStateChange,
    handleMoodUpdate,
    handleThought,
    setConnected,
    addMessage,
    updateLastAssistant,
    clearMessages,
  }
})
