<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { ChatEntry } from '@/composables/useChat'

const props = defineProps<{
  message: ChatEntry
}>()

// Configure marked for inline-friendly output
marked.setOptions({
  breaks: true,
  gfm: true,
})

const renderedContent = computed(() => {
  if (!props.message.content) return ''
  const raw = marked.parse(props.message.content) as string
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
})
</script>

<template>
  <div class="chat-message" :class="message.role">
    <div class="bubble">
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div class="content" v-html="renderedContent" />
      <span v-if="message.streaming" class="streaming-indicator">...</span>
    </div>
  </div>
</template>

<style scoped>
.chat-message {
  display: flex;
  margin-bottom: 12px;
  padding: 0 16px;
}

.chat-message.user {
  justify-content: flex-end;
}

.chat-message.assistant {
  justify-content: flex-start;
}

.bubble {
  max-width: 70%;
  padding: 10px 14px;
  border-radius: 12px;
  word-wrap: break-word;
}

.user .bubble {
  background-color: var(--color-user-bubble, #2563eb);
  color: var(--color-user-text, #ffffff);
  border-bottom-right-radius: 4px;
}

.assistant .bubble {
  background-color: var(--color-assistant-bubble, #374151);
  color: var(--color-assistant-text, #e5e7eb);
  border-bottom-left-radius: 4px;
}

.content {
  margin: 0;
  font-family: inherit;
  line-height: 1.5;
}

.content :deep(p) {
  margin: 0 0 0.5em;
}

.content :deep(p:last-child) {
  margin-bottom: 0;
}

.content :deep(code) {
  background: rgba(0, 0, 0, 0.2);
  padding: 1px 4px;
  border-radius: 3px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 0.9em;
}

.content :deep(pre) {
  background: rgba(0, 0, 0, 0.3);
  padding: 8px 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.5em 0;
}

.content :deep(pre code) {
  background: none;
  padding: 0;
}

.content :deep(blockquote) {
  border-left: 3px solid rgba(255, 255, 255, 0.2);
  margin: 0.5em 0;
  padding-left: 12px;
  opacity: 0.85;
}

.content :deep(ul),
.content :deep(ol) {
  margin: 0.5em 0;
  padding-left: 1.5em;
}

.content :deep(a) {
  color: #60a5fa;
  text-decoration: underline;
}

.content :deep(strong) {
  font-weight: 700;
}

.content :deep(del) {
  opacity: 0.6;
}

.streaming-indicator {
  display: inline-block;
  animation: blink 1s infinite;
  color: var(--color-streaming, #9ca3af);
}

@keyframes blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}
</style>
