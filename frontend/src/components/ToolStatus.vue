<script setup lang="ts">
interface Tool {
  name: string
  description: string
  enabled: boolean
  status: string
}

defineProps<{
  tools: Tool[]
}>()

const emit = defineEmits<{
  editSkill: [toolName: string]
}>()
</script>

<template>
  <div class="tool-status">
    <div v-if="tools.length === 0" class="empty-state">No tools configured</div>
    <div v-else class="tool-list">
      <div v-for="tool in tools" :key="tool.name" class="tool-item">
        <span class="status-dot" :class="tool.status"></span>
        <div class="tool-info">
          <span class="tool-name">{{ tool.name }}</span>
          <span class="tool-description">{{ tool.description }}</span>
        </div>
        <button class="skill-btn" @click="emit('editSkill', tool.name)">Edit Skill</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tool-status {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.empty-state {
  padding: 24px;
  text-align: center;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.tool-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background-color: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 6px;
}

.skill-btn {
  flex-shrink: 0;
  padding: 4px 10px;
  font-size: 11px;
  color: var(--color-text-secondary);
  background-color: transparent;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  cursor: pointer;
  transition:
    background-color 0.15s,
    color 0.15s;
}

.skill-btn:hover {
  background-color: var(--color-button);
  color: var(--color-user-text);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.available {
  background-color: #22c55e;
}

.status-dot.disabled {
  background-color: #6b7280;
}

.status-dot.error {
  background-color: #ef4444;
}

.tool-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tool-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text);
}

.tool-description {
  font-size: 12px;
  color: var(--color-text-secondary);
}
</style>
