<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { DialogueEntry } from '@/stores/workshop'

const props = defineProps<{
  entries: DialogueEntry[]
}>()

const container = ref<HTMLElement | null>(null)

marked.setOptions({
  breaks: true,
  gfm: true,
})

function renderMarkdown(content: string): string {
  const raw = marked.parse(content) as string
  return DOMPurify.sanitize(raw, {
    ALLOWED_TAGS: [
      'p',
      'br',
      'strong',
      'em',
      'code',
      'pre',
      'ul',
      'ol',
      'li',
      'blockquote',
      'a',
      'h1',
      'h2',
      'h3',
      'h4',
      'del',
    ],
    ALLOWED_ATTR: ['href', 'target', 'rel'],
  })
}

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
      <span v-if="entry.isToolEvent" class="dialogue-content">{{ entry.content }}</span>
      <!-- eslint-disable-next-line vue/no-v-html -->
      <span v-else class="dialogue-content md-content" v-html="renderMarkdown(entry.content)" />
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

.md-content :deep(p) {
  margin: 0 0 0.5em;
}
.md-content :deep(p:last-child) {
  margin-bottom: 0;
}
.md-content :deep(code) {
  background: rgba(0, 0, 0, 0.2);
  padding: 1px 4px;
  border-radius: 3px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 0.9em;
}
.md-content :deep(pre) {
  background: rgba(0, 0, 0, 0.3);
  padding: 8px 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.5em 0;
}
.md-content :deep(pre code) {
  background: none;
  padding: 0;
}
.md-content :deep(blockquote) {
  border-left: 3px solid rgba(255, 255, 255, 0.2);
  margin: 0.5em 0;
  padding-left: 12px;
  opacity: 0.85;
}
.md-content :deep(ul),
.md-content :deep(ol) {
  margin: 0.5em 0;
  padding-left: 1.5em;
}
.md-content :deep(a) {
  color: #60a5fa;
  text-decoration: underline;
}
.md-content :deep(strong) {
  font-weight: 700;
}
.md-content :deep(del) {
  opacity: 0.6;
}
</style>
