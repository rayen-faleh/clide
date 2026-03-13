<script setup lang="ts">
interface Goal {
  description: string
  priority: string
  status: string
  progress: number
}

defineProps<{
  goals: Goal[]
}>()

function priorityClass(priority: string): string {
  return `priority-${priority}`
}

function progressPercent(progress: number): string {
  return `${Math.round(progress * 100)}%`
}
</script>

<template>
  <div class="goal-tracker">
    <h3 class="goal-tracker-title">Goals</h3>
    <div v-if="goals.length === 0" class="goal-empty">No goals yet</div>
    <div v-else class="goal-list">
      <div
        v-for="(goal, index) in goals"
        :key="index"
        class="goal-item"
        :class="{ active: goal.status === 'active' }"
      >
        <div class="goal-header">
          <span class="goal-description">{{ goal.description }}</span>
          <span class="goal-priority" :class="priorityClass(goal.priority)">
            {{ goal.priority }}
          </span>
        </div>
        <div class="goal-progress-bar">
          <div class="goal-progress-fill" :style="{ width: progressPercent(goal.progress) }"></div>
        </div>
        <div class="goal-meta">
          <span class="goal-status">{{ goal.status }}</span>
          <span class="goal-percent">{{ progressPercent(goal.progress) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.goal-tracker {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: var(--color-surface);
  border-radius: 8px;
  border: 1px solid var(--color-border);
  overflow: hidden;
}

.goal-tracker-title {
  padding: 12px 16px;
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  border-bottom: 1px solid var(--color-border);
}

.goal-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: var(--color-text-secondary);
  font-size: 13px;
  font-style: italic;
}

.goal-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.goal-item {
  padding: 10px 12px;
  border-radius: 6px;
  margin-bottom: 6px;
  background-color: rgba(255, 255, 255, 0.03);
  border: 1px solid transparent;
}

.goal-item.active {
  border-color: var(--color-border);
}

.goal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.goal-description {
  font-size: 13px;
  color: var(--color-text);
  font-weight: 500;
}

.goal-priority {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 600;
}

.priority-high {
  background-color: rgba(239, 68, 68, 0.2);
  color: #f87171;
}

.priority-medium {
  background-color: rgba(234, 179, 8, 0.2);
  color: #fbbf24;
}

.priority-low {
  background-color: rgba(34, 197, 94, 0.2);
  color: #4ade80;
}

.goal-progress-bar {
  height: 4px;
  background-color: var(--color-border);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 6px;
}

.goal-progress-fill {
  height: 100%;
  background-color: #3b82f6;
  border-radius: 2px;
  transition: width 0.3s ease;
}

.goal-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--color-text-secondary);
}

.goal-status {
  text-transform: capitalize;
}
</style>
