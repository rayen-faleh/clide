import { defineStore } from 'pinia'
import { ref } from 'vue'
import type {
  AgentState,
  MoodPayload,
  ToolCallPayload,
  ToolResultPayload,
  WSMessage,
} from '@/types/messages'

export interface ChatEntry {
  id: string
  content: string
  role: 'user' | 'assistant'
  timestamp: Date
  streaming?: boolean
}

export interface ToolEvent {
  id: string
  type: 'tool'
  tool_name: string
  arguments: Record<string, unknown>
  call_id: string
  result?: unknown
  error?: string | null
  status: 'executing' | 'success' | 'error'
  timestamp: Date
}

export type MessageItem = ChatEntry | ToolEvent

export interface ThoughtEntry {
  content: string
  source: string
  timestamp: string
}

export const useAgentStore = defineStore('agent', () => {
  const state = ref<AgentState>('idle')
  const mood = ref<MoodPayload | null>(null)
  const currentThought = ref<string | null>(null)
  const thoughts = ref<ThoughtEntry[]>([])
  const connected = ref(false)

  // Chat state — persists across navigation
  const messages = ref<MessageItem[]>([])
  const isStreaming = ref(false)

  function handleStateChange(msg: WSMessage) {
    const payload = msg.payload as { new_state: AgentState }
    state.value = payload.new_state
  }

  function handleMoodUpdate(msg: WSMessage) {
    mood.value = msg.payload as unknown as MoodPayload
  }

  function handleThought(msg: WSMessage) {
    const payload = msg.payload as { content: string; source?: string }
    currentThought.value = payload.content
    thoughts.value.push({
      content: payload.content,
      source: payload.source ?? 'autonomous',
      timestamp: msg.timestamp,
    })
  }

  function setConnected(value: boolean) {
    connected.value = value
  }

  function addMessage(entry: ChatEntry) {
    messages.value.push(entry)
  }

  function updateLastAssistant(content: string, done: boolean) {
    const lastAssistant = [...messages.value]
      .reverse()
      .find((m): m is ChatEntry => !('type' in m && m.type === 'tool') && m.role === 'assistant')
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

  function handleToolCall(msg: WSMessage) {
    const payload = msg.payload as unknown as ToolCallPayload
    const event: ToolEvent = {
      id: crypto.randomUUID(),
      type: 'tool',
      tool_name: payload.tool_name,
      arguments: payload.arguments,
      call_id: payload.call_id,
      status: 'executing',
      timestamp: new Date(),
    }
    messages.value.push(event)
  }

  function handleToolResult(msg: WSMessage) {
    const payload = msg.payload as unknown as ToolResultPayload
    const event = [...messages.value]
      .reverse()
      .find(
        (m): m is ToolEvent => 'type' in m && m.type === 'tool' && m.call_id === payload.call_id,
      )
    if (event) {
      event.result = payload.result
      event.error = payload.error
      event.status = payload.error ? 'error' : 'success'
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
    thoughts,
    connected,
    messages,
    isStreaming,
    handleStateChange,
    handleMoodUpdate,
    handleThought,
    setConnected,
    addMessage,
    updateLastAssistant,
    handleToolCall,
    handleToolResult,
    clearMessages,
  }
})
