<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  disabled?: boolean
}>()

const emit = defineEmits<{
  send: [content: string]
}>()

const input = ref('')

function handleSend() {
  const content = input.value.trim()
  if (!content) return
  emit('send', content)
  input.value = ''
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSend()
  }
}
</script>

<template>
  <div class="chat-input">
    <textarea
      v-model="input"
      :disabled="disabled"
      placeholder="Type a message..."
      rows="2"
      @keydown="handleKeydown"
    />
    <button :disabled="disabled" @click="handleSend">Send</button>
  </div>
</template>

<style scoped>
.chat-input {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--color-border, #374151);
  background-color: var(--color-input-bg, #1f2937);
}

textarea {
  flex: 1;
  resize: none;
  padding: 8px 12px;
  border: 1px solid var(--color-border, #4b5563);
  border-radius: 8px;
  background-color: var(--color-textarea-bg, #111827);
  color: var(--color-text, #e5e7eb);
  font-family: inherit;
  font-size: 14px;
  line-height: 1.4;
}

textarea:focus {
  outline: none;
  border-color: var(--color-focus, #2563eb);
}

textarea:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

button {
  padding: 8px 20px;
  border: none;
  border-radius: 8px;
  background-color: var(--color-button, #2563eb);
  color: #ffffff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  align-self: flex-end;
}

button:hover:not(:disabled) {
  background-color: var(--color-button-hover, #1d4ed8);
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
