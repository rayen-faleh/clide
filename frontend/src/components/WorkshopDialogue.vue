<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import type { DialogueEntry } from '@/stores/workshop'

const props = defineProps<{
  entries: DialogueEntry[]
}>()

const container = ref<HTMLElement | null>(null)

watch(
  () => props.entries.length,
  () => {
    nextTick(() => {
      if (container.value) {
        container.value.scrollTop = container.value.scrollHeight
      }
    })
  },
)
</script>

<template>
  <div ref="container" class="dialogue-container">
    <div v-if="entries.length === 0" class="dialogue-empty">Waiting for agent to begin...</div>
    <div
      v-for="entry in entries"
      :key="entry.id"
      class="dialogue-entry"
      :class="{ 'tool-event': entry.isToolEvent }"
    >
      <span class="dialogue-content">{{ entry.content }}</span>
    </div>
  </div>
</template>

<style scoped>
.dialogue-container {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  height: 100%;
}
.dialogue-empty {
  color: var(--color-text-secondary, #6b7280);
  font-size: 0.85rem;
  padding: 16px;
}
.dialogue-entry {
  display: flex;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 0.85rem;
  line-height: 1.5;
  color: var(--color-text, #e5e7eb);
  background: var(--color-assistant-bubble, #374151);
}
.dialogue-entry.tool-event {
  background: rgba(100, 181, 246, 0.08);
  color: #64b5f6;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 0.8rem;
}
.dialogue-content {
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
