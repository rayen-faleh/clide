<script setup lang="ts">
import type { ThoughtEntry } from '@/stores/agent'

defineProps<{
  thoughts: ThoughtEntry[]
}>()

function formatTime(iso: string): string {
  const date = new Date(iso)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="thought-stream">
    <h3 class="thought-stream-title">Thought Stream</h3>
    <div v-if="thoughts.length === 0" class="thought-empty">No thoughts yet</div>
    <div v-else class="thought-list" ref="listRef">
      <div v-for="(thought, index) in thoughts" :key="index" class="thought-entry">
        <span class="thought-time">{{ formatTime(thought.timestamp) }}</span>
        <span class="thought-content">{{ thought.content }}</span>
        <span v-if="thought.source === 'autonomous'" class="thought-badge">auto</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.thought-stream {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: var(--color-surface);
  border-radius: 8px;
  border: 1px solid var(--color-border);
  overflow: hidden;
}

.thought-stream-title {
  padding: 12px 16px;
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  border-bottom: 1px solid var(--color-border);
}

.thought-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: var(--color-text-secondary);
  font-size: 13px;
  font-style: italic;
}

.thought-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.thought-entry {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 16px;
  font-family: 'SF Mono', 'Fira Code', 'Fira Mono', Menlo, monospace;
  font-size: 12px;
  line-height: 1.5;
}

.thought-entry:hover {
  background-color: rgba(255, 255, 255, 0.03);
}

.thought-time {
  color: var(--color-text-secondary);
  flex-shrink: 0;
  font-size: 11px;
}

.thought-content {
  color: var(--color-text);
  flex: 1;
}

.thought-badge {
  flex-shrink: 0;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background-color: rgba(99, 102, 241, 0.2);
  color: #818cf8;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
</style>
