<script setup lang="ts">
import type { ChatEntry } from '@/composables/useChat'

defineProps<{
  message: ChatEntry
}>()
</script>

<template>
  <div class="chat-message" :class="message.role">
    <div class="bubble">
      <p class="content">{{ message.content }}</p>
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
  white-space: pre-wrap;
  font-family: inherit;
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
