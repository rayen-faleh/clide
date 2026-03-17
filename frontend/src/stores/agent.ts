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

export interface CheckpointEntry {
  id: string
  type: 'checkpoint'
  content: string
  phase: number
  totalPhases: number
  timestamp: Date
}

export type MessageItem = ChatEntry | ToolEvent | CheckpointEntry

export interface ThoughtToolEvent {
  tool_name: string
  arguments: Record<string, unknown>
  call_id: string
  result?: unknown
  error?: string | null
}

export interface ThoughtEntry {
  content: string
  source: string
  thoughtType?: string
  timestamp: string
  toolEvents?: ThoughtToolEvent[]
}

const TOOL_EVENTS_KEY = 'clide_tool_events'

function persistToolEvents(messages: MessageItem[]): void {
  const toolEvents = messages
    .filter((m): m is ToolEvent => 'type' in m && m.type === 'tool')
    .slice(-100)
  try {
    localStorage.setItem(TOOL_EVENTS_KEY, JSON.stringify(toolEvents))
  } catch (e) {
    console.warn('Failed to persist tool events:', e)
  }
}

function loadPersistedToolEvents(): ToolEvent[] {
  try {
    const raw = localStorage.getItem(TOOL_EVENTS_KEY)
    if (!raw) return []
    const events = JSON.parse(raw) as ToolEvent[]
    return events.map((e) => ({ ...e, timestamp: new Date(e.timestamp) }))
  } catch (e) {
    console.warn('Failed to load persisted tool events:', e)
    return []
  }
}

export const useAgentStore = defineStore('agent', () => {
  const state = ref<AgentState>('idle')
  const mood = ref<MoodPayload | null>(null)
  const currentThought = ref<string | null>(null)
  const thoughts = ref<ThoughtEntry[]>([])
  const connected = ref(false)

  // Pending tool events that occur during thinking, before a thought arrives
  const pendingThinkingTools = ref<ThoughtToolEvent[]>([])

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
    const payload = msg.payload as { content: string; source?: string; thought_type?: string }
    currentThought.value = payload.content
    thoughts.value.push({
      content: payload.content,
      source: payload.source ?? 'autonomous',
      thoughtType: payload.thought_type,
      timestamp: msg.timestamp,
      toolEvents:
        pendingThinkingTools.value.length > 0 ? [...pendingThinkingTools.value] : undefined,
    })
    pendingThinkingTools.value = []
  }

  function handleThinkingToolCall(msg: WSMessage) {
    const payload = msg.payload as unknown as ToolCallPayload
    pendingThinkingTools.value.push({
      tool_name: payload.tool_name,
      arguments: payload.arguments,
      call_id: payload.call_id,
    })
  }

  function handleThinkingToolResult(msg: WSMessage) {
    const payload = msg.payload as unknown as ToolResultPayload
    const event = pendingThinkingTools.value.find((e) => e.call_id === payload.call_id)
    if (event) {
      event.result = payload.result
      event.error = payload.error
    }
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
    // Only add to chat messages if agent is not thinking — during thinking,
    // DashboardView's handleThinkingToolCall handles it via pendingThinkingTools
    if (state.value === 'thinking') {
      return
    }
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
    persistToolEvents(messages.value)
  }

  function handleToolResult(msg: WSMessage) {
    // Skip chat message update during thinking — dashboard handles it
    if (state.value === 'thinking') {
      return
    }
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
      persistToolEvents(messages.value)
    }
  }

  function handleToolCheckpoint(msg: WSMessage) {
    const payload = msg.payload as { content: string; phase: number; total_phases: number }
    messages.value.push({
      id: crypto.randomUUID(),
      type: 'checkpoint',
      content: payload.content,
      phase: payload.phase,
      totalPhases: payload.total_phases,
      timestamp: new Date(),
    })
  }

  function restoreToolEvents(): void {
    const persisted = loadPersistedToolEvents()
    for (const event of persisted) {
      // Avoid duplicates
      const exists = messages.value.some(
        (m) => 'type' in m && m.type === 'tool' && (m as ToolEvent).call_id === event.call_id,
      )
      if (exists) continue

      const insertIndex = messages.value.findIndex((m) => {
        const msgTime = 'timestamp' in m ? new Date(m.timestamp) : new Date(0)
        return msgTime > event.timestamp
      })
      if (insertIndex === -1) {
        messages.value.push(event)
      } else {
        messages.value.splice(insertIndex, 0, event)
      }
    }
  }

  function clearMessages() {
    messages.value = []
    isStreaming.value = false
    try {
      localStorage.removeItem(TOOL_EVENTS_KEY)
    } catch (e) {
      console.warn('Failed to clear tool events from localStorage:', e)
    }
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
    handleThinkingToolCall,
    handleThinkingToolResult,
    setConnected,
    addMessage,
    updateLastAssistant,
    handleToolCall,
    handleToolResult,
    handleToolCheckpoint,
    restoreToolEvents,
    clearMessages,
  }
})
