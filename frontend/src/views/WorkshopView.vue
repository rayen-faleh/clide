<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { useWorkshopStore } from '@/stores/workshop'
import { useAgentStore } from '@/stores/agent'
import type { WSMessage } from '@/types/messages'
import WorkshopPlanPanel from '@/components/WorkshopPlan.vue'
import WorkshopDialogue from '@/components/WorkshopDialogue.vue'

const { on, off, connect } = useWebSocket()
const workshopStore = useWorkshopStore()
const agentStore = useAgentStore()

function handleStarted(msg: WSMessage) {
  workshopStore.handleWorkshopStarted(msg)
}
function handlePlan(msg: WSMessage) {
  workshopStore.handleWorkshopPlan(msg)
}
function handleDialogue(msg: WSMessage) {
  workshopStore.handleWorkshopDialogue(msg)
}
function handleStepUpdate(msg: WSMessage) {
  workshopStore.handleWorkshopStepUpdate(msg)
}
function handleEnded(msg: WSMessage) {
  workshopStore.handleWorkshopEnded(msg)
}
function handleStateChange(msg: WSMessage) {
  agentStore.handleStateChange(msg)
}
function handleToolCall(msg: WSMessage) {
  const payload = msg.payload as { tool_name: string }
  workshopStore.handleWorkshopDialogue({
    ...msg,
    payload: {
      session_id: workshopStore.session?.id ?? '',
      content: `Tool: ${payload.tool_name}(...)`,
      is_tool_event: true,
    },
  })
}
function handleToolResult(msg: WSMessage) {
  const payload = msg.payload as { result?: unknown; error?: string | null }
  const preview = payload.result ? String(payload.result).slice(0, 100) : payload.error || 'done'
  workshopStore.handleWorkshopDialogue({
    ...msg,
    payload: {
      session_id: workshopStore.session?.id ?? '',
      content: `   -> ${preview}`,
      is_tool_event: true,
    },
  })
}

async function handleDiscard() {
  await workshopStore.discardWorkshop()
}

onMounted(async () => {
  await workshopStore.loadSession()

  on('workshop_started', handleStarted)
  on('workshop_plan', handlePlan)
  on('workshop_dialogue', handleDialogue)
  on('workshop_step_update', handleStepUpdate)
  on('workshop_ended', handleEnded)
  on('state_change', handleStateChange)
  on('tool_call', handleToolCall)
  on('tool_result', handleToolResult)

  connect()
})

onUnmounted(() => {
  off('workshop_started', handleStarted)
  off('workshop_plan', handlePlan)
  off('workshop_dialogue', handleDialogue)
  off('workshop_step_update', handleStepUpdate)
  off('workshop_ended', handleEnded)
  off('state_change', handleStateChange)
  off('tool_call', handleToolCall)
  off('tool_result', handleToolResult)
})
</script>

<template>
  <div class="workshop-view">
    <div class="workshop-header">
      <h2 class="workshop-title">Workshop</h2>
      <div class="workshop-meta">
        <span
          v-if="workshopStore.session"
          class="workshop-status"
          :class="workshopStore.session.status"
        >
          {{ workshopStore.session.status }}
        </span>
        <span v-if="workshopStore.session" class="workshop-goal">
          {{ workshopStore.session.goalDescription }}
        </span>
      </div>
      <button v-if="workshopStore.isActive" class="discard-btn" @click="handleDiscard">
        Discard
      </button>
    </div>

    <div v-if="!workshopStore.session" class="workshop-empty">
      <p>No active workshop session.</p>
      <p class="workshop-hint">
        The agent will enter Workshop mode when a goal-oriented thought triggers a productivity
        surge.
      </p>
    </div>

    <div v-else class="workshop-content">
      <div class="workshop-plan-panel">
        <WorkshopPlanPanel
          v-if="workshopStore.session.plan"
          :plan="workshopStore.session.plan"
          :current-step="workshopStore.session.currentStepIndex"
        />
        <div v-else class="plan-loading">Generating plan...</div>
      </div>
      <div class="workshop-dialogue-panel">
        <WorkshopDialogue :entries="workshopStore.session.dialogue" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.workshop-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.workshop-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border, #374151);
}

.workshop-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text, #e5e7eb);
  margin: 0;
}

.workshop-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.workshop-status {
  font-size: 0.7rem;
  padding: 2px 8px;
  border-radius: 10px;
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.5px;
}
.workshop-status.active {
  background: rgba(34, 197, 94, 0.2);
  color: #4ade80;
}
.workshop-status.paused {
  background: rgba(234, 179, 8, 0.2);
  color: #facc15;
}
.workshop-status.completed {
  background: rgba(59, 130, 246, 0.2);
  color: #60a5fa;
}
.workshop-status.abandoned {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
}

.workshop-goal {
  font-size: 0.85rem;
  color: var(--color-text-secondary, #9ca3af);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.discard-btn {
  padding: 6px 16px;
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid #ef4444;
  border-radius: 6px;
  color: #f87171;
  font-size: 0.8rem;
  cursor: pointer;
  transition: background 0.2s;
}
.discard-btn:hover {
  background: rgba(239, 68, 68, 0.3);
}

.workshop-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--color-text-secondary, #6b7280);
}
.workshop-hint {
  font-size: 0.8rem;
  opacity: 0.6;
  max-width: 400px;
  text-align: center;
}

.workshop-content {
  display: flex;
  flex: 1;
  min-height: 0;
}

.workshop-plan-panel {
  width: 300px;
  min-width: 250px;
  border-right: 1px solid var(--color-border, #374151);
  overflow-y: auto;
  padding: 16px;
}

.workshop-dialogue-panel {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
}

.plan-loading {
  color: var(--color-text-secondary, #9ca3af);
  font-size: 0.85rem;
  padding: 16px;
}
</style>
