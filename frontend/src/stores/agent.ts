import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AgentState, MoodPayload, WSMessage } from '@/types/messages'

export const useAgentStore = defineStore('agent', () => {
  const state = ref<AgentState>('idle')
  const mood = ref<MoodPayload | null>(null)
  const currentThought = ref<string | null>(null)
  const connected = ref(false)

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

  return {
    state,
    mood,
    currentThought,
    connected,
    handleStateChange,
    handleMoodUpdate,
    handleThought,
    setConnected,
  }
})
