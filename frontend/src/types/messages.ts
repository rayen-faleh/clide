export type WSMessageType =
  | 'chat_message'
  | 'chat_response'
  | 'chat_response_chunk'
  | 'thought'
  | 'mood_update'
  | 'memory_update'
  | 'tool_call'
  | 'tool_result'
  | 'tool_checkpoint'
  | 'reward_given'
  | 'state_change'
  | 'status'
  | 'error'
  | 'workshop_started'
  | 'workshop_plan'
  | 'workshop_dialogue'
  | 'workshop_step_update'
  | 'workshop_ended'

export type AgentState = 'sleeping' | 'idle' | 'thinking' | 'conversing' | 'working' | 'workshop'

export interface WSMessage {
  type: WSMessageType
  payload: Record<string, unknown>
  timestamp: string
}

export interface ChatMessagePayload {
  content: string
  role: 'user' | 'assistant'
}

export interface ChatResponseChunkPayload {
  content: string
  done: boolean
}

export interface ThoughtPayload {
  content: string
  source: 'autonomous' | 'reactive'
}

export interface MoodPayload {
  mood: string
  intensity: number
  reason: string
}

export interface StateChangePayload {
  previous_state: AgentState
  new_state: AgentState
  reason: string
}

export interface ToolCallPayload {
  tool_name: string
  arguments: Record<string, unknown>
  call_id: string
}

export interface ToolResultPayload {
  call_id: string
  result: unknown
  error: string | null
}

export interface ErrorPayload {
  message: string
  code: string
}
