<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useAgentStore } from '@/stores/agent'
import { useWebSocket } from '@/composables/useWebSocket'
import AgentStateIndicator from '@/components/AgentStateIndicator.vue'
import MoodDisplay from '@/components/MoodDisplay.vue'
import ThoughtStream from '@/components/ThoughtStream.vue'
import GoalTracker from '@/components/GoalTracker.vue'
import type { WSMessage } from '@/types/messages'

interface Goal {
  description: string
  priority: string
  status: string
  progress: number
}

const agentStore = useAgentStore()
const { connect, on, off } = useWebSocket()

const goals = ref<Goal[]>([])

async function fetchGoals() {
  try {
    const res = await fetch('/api/goals/active')
    if (res.ok) {
      const data = await res.json()
      goals.value = data.goals
    }
  } catch (e) {
    console.error('Failed to load goals:', e)
  }
}

function handleThought(msg: WSMessage) {
  agentStore.handleThought(msg)
  // Refresh goals after each thought (goals may have been created/updated)
  fetchGoals()
}

function handleMoodUpdate(msg: WSMessage) {
  agentStore.handleMoodUpdate(msg)
}

function handleStateChange(msg: WSMessage) {
  agentStore.handleStateChange(msg)
  // Refresh goals on state changes (thinking cycle may have modified goals)
  fetchGoals()
}

function handleThinkingToolCall(msg: WSMessage) {
  agentStore.handleThinkingToolCall(msg)
}

function handleThinkingToolResult(msg: WSMessage) {
  agentStore.handleThinkingToolResult(msg)
}

onMounted(() => {
  fetchGoals()
  on('thought', handleThought)
  on('mood_update', handleMoodUpdate)
  on('state_change', handleStateChange)
  on('tool_call', handleThinkingToolCall)
  on('tool_result', handleThinkingToolResult)
  connect()
})

onUnmounted(() => {
  off('thought', handleThought)
  off('mood_update', handleMoodUpdate)
  off('state_change', handleStateChange)
  off('tool_call', handleThinkingToolCall)
  off('tool_result', handleThinkingToolResult)
})
</script>

<template>
  <div class="dashboard-view">
    <div class="dashboard-header">
      <AgentStateIndicator :state="agentStore.state" />
      <MoodDisplay
        :mood="agentStore.mood?.mood ?? 'neutral'"
        :intensity="agentStore.mood?.intensity ?? 0.5"
      />
    </div>
    <div class="dashboard-body">
      <ThoughtStream :thoughts="agentStore.thoughts" class="dashboard-thoughts" />
      <GoalTracker :goals="goals" class="dashboard-goals" />
    </div>
  </div>
</template>

<style scoped>
.dashboard-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
  gap: 16px;
}

.dashboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background-color: var(--color-surface);
  border-radius: 8px;
  border: 1px solid var(--color-border);
}

.dashboard-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.dashboard-thoughts {
  min-height: 0;
}

.dashboard-goals {
  min-height: 0;
}
</style>
