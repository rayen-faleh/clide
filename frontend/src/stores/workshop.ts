import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { WSMessage } from '@/types/messages'

export interface WorkshopStep {
  id: string
  description: string
  toolsNeeded: string[]
  successCriteria: string
  status: 'pending' | 'in_progress' | 'completed' | 'skipped'
  resultSummary: string
}

export interface WorkshopPlan {
  objective: string
  approach: string
  steps: WorkshopStep[]
}

export interface DialogueEntry {
  id: string
  content: string
  timestamp: Date
  isToolEvent?: boolean
}

export interface WorkshopSession {
  id: string
  goalDescription: string
  status: 'active' | 'paused' | 'completed' | 'abandoned'
  plan: WorkshopPlan | null
  currentStepIndex: number
  dialogue: DialogueEntry[]
}

export const useWorkshopStore = defineStore('workshop', () => {
  const session = ref<WorkshopSession | null>(null)
  const isActive = computed(
    () => session.value?.status === 'active' || session.value?.status === 'paused',
  )

  function handleWorkshopStarted(msg: WSMessage) {
    const payload = msg.payload as { session_id: string; goal_description: string }
    session.value = {
      id: payload.session_id,
      goalDescription: payload.goal_description,
      status: 'active',
      plan: null,
      currentStepIndex: 0,
      dialogue: [],
    }
  }

  function handleWorkshopPlan(msg: WSMessage) {
    const payload = msg.payload as {
      session_id: string
      objective: string
      approach: string
      steps: Array<{
        id: string
        description: string
        tools_needed: string[]
        success_criteria: string
        status: string
      }>
    }
    if (!session.value) return
    session.value.plan = {
      objective: payload.objective,
      approach: payload.approach,
      steps: payload.steps.map((s) => ({
        id: s.id,
        description: s.description,
        toolsNeeded: s.tools_needed,
        successCriteria: s.success_criteria,
        status: s.status as WorkshopStep['status'],
        resultSummary: '',
      })),
    }
  }

  function handleWorkshopDialogue(msg: WSMessage) {
    const payload = msg.payload as {
      session_id: string
      content: string
      is_tool_event?: boolean
    }
    if (!session.value) return
    session.value.dialogue.push({
      id: crypto.randomUUID(),
      content: payload.content,
      timestamp: new Date(),
      isToolEvent: payload.is_tool_event,
    })
    // Cap dialogue at 200 entries
    if (session.value.dialogue.length > 200) {
      session.value.dialogue = session.value.dialogue.slice(-200)
    }
  }

  function handleWorkshopStepUpdate(msg: WSMessage) {
    const payload = msg.payload as {
      session_id: string
      step_index: number
      status: string
      result_summary: string
    }
    if (!session.value?.plan) return
    const step = session.value.plan.steps[payload.step_index]
    if (step) {
      step.status = payload.status as WorkshopStep['status']
      step.resultSummary = payload.result_summary
      session.value.currentStepIndex = payload.step_index
    }
  }

  function handleWorkshopEnded(msg: WSMessage) {
    // Clear session when workshop ends (completed, abandoned, or discarded)
    session.value = null
  }

  async function discardWorkshop(): Promise<void> {
    try {
      await fetch('/api/workshop/discard', { method: 'POST' })
    } catch (e) {
      console.error('Failed to discard workshop:', e)
    }
    // Clear local state immediately
    session.value = null
  }

  function clearSession() {
    session.value = null
  }

  async function loadSession(): Promise<void> {
    try {
      const res = await fetch('/api/workshop/session')
      if (res.ok) {
        const data = (await res.json()) as {
          session: {
            id: string
            goal_description: string
            status: string
            current_step_index: number
            plan: {
              objective: string
              approach: string
              steps: Array<{
                id: string
                description: string
                tools_needed: string[]
                success_criteria: string
                status: string
                result_summary: string
              }>
            } | null
            inner_dialogue: Array<{
              content: string
              timestamp: string
            }>
          } | null
        }
        if (data.session) {
          session.value = {
            id: data.session.id,
            goalDescription: data.session.goal_description,
            status: data.session.status as WorkshopSession['status'],
            currentStepIndex: data.session.current_step_index,
            plan: data.session.plan
              ? {
                  objective: data.session.plan.objective,
                  approach: data.session.plan.approach,
                  steps: data.session.plan.steps.map((s) => ({
                    id: s.id,
                    description: s.description,
                    toolsNeeded: s.tools_needed,
                    successCriteria: s.success_criteria,
                    status: s.status as WorkshopStep['status'],
                    resultSummary: s.result_summary,
                  })),
                }
              : null,
            dialogue: (data.session.inner_dialogue || []).map((d) => ({
              id: crypto.randomUUID(),
              content: d.content,
              timestamp: new Date(d.timestamp),
            })),
          }
        }
      }
    } catch (e) {
      console.warn('Failed to load workshop session:', e)
    }
  }

  return {
    session,
    isActive,
    handleWorkshopStarted,
    handleWorkshopPlan,
    handleWorkshopDialogue,
    handleWorkshopStepUpdate,
    handleWorkshopEnded,
    discardWorkshop,
    clearSession,
    loadSession,
  }
})
