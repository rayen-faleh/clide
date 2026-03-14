<script setup lang="ts">
import { ref } from 'vue'
import type { ToolEvent } from '@/stores/agent'

defineProps<{
  event: ToolEvent
}>()

const expanded = ref(false)
</script>

<template>
  <div class="tool-card" :class="event.status">
    <div class="tool-header" @click="expanded = !expanded">
      <span class="tool-icon">
        <span v-if="event.status === 'executing'" class="spinner">&#9881;</span>
        <span v-else-if="event.status === 'success'">&#10003;</span>
        <span v-else>&#10007;</span>
      </span>
      <span class="tool-name">{{ event.tool_name }}</span>
      <span class="tool-status">{{ event.status }}</span>
      <span class="expand-icon">{{ expanded ? '\u25BC' : '\u25B6' }}</span>
    </div>
    <div v-if="expanded" class="tool-details">
      <div class="tool-section">
        <div class="tool-label">Arguments</div>
        <pre class="tool-json">{{ JSON.stringify(event.arguments, null, 2) }}</pre>
      </div>
      <div v-if="event.result !== undefined" class="tool-section">
        <div class="tool-label">Result</div>
        <pre class="tool-json">{{
          typeof event.result === 'string' ? event.result : JSON.stringify(event.result, null, 2)
        }}</pre>
      </div>
      <div v-if="event.error" class="tool-section error">
        <div class="tool-label">Error</div>
        <pre class="tool-json">{{ event.error }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tool-card {
  margin: 0.5rem 1rem;
  border-radius: 8px;
  border: 1px solid var(--color-border, #333);
  background: var(--color-surface, #1a1a2e);
  font-size: 0.85rem;
  overflow: hidden;
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  cursor: pointer;
  user-select: none;
}

.tool-header:hover {
  background: rgba(255, 255, 255, 0.05);
}

.tool-icon {
  font-size: 1rem;
}

.tool-card.executing .tool-icon {
  animation: spin 1s linear infinite;
}

.tool-card.success .tool-icon {
  color: #4caf50;
}

.tool-card.error .tool-icon {
  color: #f44336;
}

.tool-name {
  font-weight: 600;
  color: #64b5f6;
}

.tool-status {
  margin-left: auto;
  font-size: 0.75rem;
  opacity: 0.6;
  text-transform: uppercase;
}

.expand-icon {
  font-size: 0.7rem;
  opacity: 0.5;
}

.tool-details {
  padding: 0 0.75rem 0.75rem;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.tool-section {
  margin-top: 0.5rem;
}

.tool-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  opacity: 0.5;
  margin-bottom: 0.25rem;
}

.tool-json {
  background: rgba(0, 0, 0, 0.3);
  padding: 0.5rem;
  border-radius: 4px;
  font-family: monospace;
  font-size: 0.8rem;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
}

.tool-section.error .tool-json {
  color: #f44336;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
