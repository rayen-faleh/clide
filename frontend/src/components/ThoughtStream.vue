<script setup lang="ts">
import { ref } from 'vue'
import type { ThoughtEntry } from '@/stores/agent'

defineProps<{
  thoughts: ThoughtEntry[]
}>()

const expandedThoughts = ref(new Set<string>())

function formatTime(iso: string): string {
  const date = new Date(iso)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function toggleToolDetails(thought: ThoughtEntry) {
  if (expandedThoughts.value.has(thought.timestamp)) {
    expandedThoughts.value.delete(thought.timestamp)
  } else {
    expandedThoughts.value.add(thought.timestamp)
  }
}

function formatResult(result: unknown): string {
  const text = typeof result === 'string' ? result : JSON.stringify(result)
  return text.length > 200 ? text.slice(0, 200) + '...' : text
}
</script>

<template>
  <div class="thought-stream">
    <h3 class="thought-stream-title">Thought Stream</h3>
    <div v-if="thoughts.length === 0" class="thought-empty">No thoughts yet</div>
    <div v-else class="thought-list" ref="listRef">
      <div v-for="(thought, index) in thoughts" :key="index" class="thought-entry">
        <div class="thought-row">
          <span class="thought-time">{{ formatTime(thought.timestamp) }}</span>
          <span class="thought-content">{{ thought.content }}</span>
          <span v-if="thought.source === 'autonomous'" class="thought-badge">auto</span>
          <span
            v-if="thought.toolEvents?.length"
            class="tool-badge"
            @click="toggleToolDetails(thought)"
          >
            &#128295; {{ thought.toolEvents.length }} tool(s) used
          </span>
        </div>
        <div
          v-if="thought.toolEvents?.length && expandedThoughts.has(thought.timestamp)"
          class="thought-tools"
        >
          <div v-for="tool in thought.toolEvents" :key="tool.call_id" class="thought-tool-item">
            <div class="tool-name">{{ tool.tool_name }}</div>
            <div class="tool-args">{{ JSON.stringify(tool.arguments) }}</div>
            <div v-if="tool.result !== undefined" class="tool-result-preview">
              {{ formatResult(tool.result) }}
            </div>
            <div v-if="tool.error" class="tool-error">{{ tool.error }}</div>
          </div>
        </div>
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
  padding: 8px 16px;
  font-family: 'SF Mono', 'Fira Code', 'Fira Mono', Menlo, monospace;
  font-size: 12px;
  line-height: 1.5;
}

.thought-entry:hover {
  background-color: rgba(255, 255, 255, 0.03);
}

.thought-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
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

.tool-badge {
  flex-shrink: 0;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background-color: rgba(100, 181, 246, 0.15);
  color: #64b5f6;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}

.tool-badge:hover {
  background-color: rgba(100, 181, 246, 0.25);
}

.thought-tools {
  margin-top: 6px;
  margin-left: 52px;
  padding: 6px 8px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.thought-tool-item {
  padding: 4px 0;
}

.thought-tool-item + .thought-tool-item {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  margin-top: 4px;
  padding-top: 8px;
}

.tool-name {
  font-weight: 600;
  color: #64b5f6;
  font-size: 11px;
}

.tool-args {
  color: var(--color-text-secondary);
  font-size: 10px;
  margin-top: 2px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.tool-result-preview {
  color: var(--color-text-secondary);
  font-size: 10px;
  margin-top: 4px;
  background: rgba(0, 0, 0, 0.2);
  padding: 4px 6px;
  border-radius: 3px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 120px;
  overflow-y: auto;
}

.tool-error {
  color: #f44336;
  font-size: 10px;
  margin-top: 4px;
}
</style>
