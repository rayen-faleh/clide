<script setup lang="ts">
import { onMounted, onUnmounted, watch, ref, nextTick } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { useChat } from '@/composables/useChat'
import { useAgentStore } from '@/stores/agent'
import type { WSMessage } from '@/types/messages'
import ChatMessage from '@/components/ChatMessage.vue'
import ChatInput from '@/components/ChatInput.vue'

const { status, connect, send, on, off } = useWebSocket()
const { messages, isStreaming, sendMessage, handleResponseChunk } = useChat(send)
const agentStore = useAgentStore()

const messagesContainer = ref<HTMLElement | null>(null)

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

watch(
  () => messages.value.length,
  () => scrollToBottom(),
)

watch(
  () => messages.value[messages.value.length - 1]?.content,
  () => scrollToBottom(),
)

function handleStateChange(msg: WSMessage) {
  agentStore.handleStateChange(msg)
}

function handleMoodUpdate(msg: WSMessage) {
  agentStore.handleMoodUpdate(msg)
}

function handleThought(msg: WSMessage) {
  agentStore.handleThought(msg)
}

onMounted(async () => {
  // Load persisted history if store is empty
  if (agentStore.messages.length === 0) {
    try {
      const res = await fetch('/api/conversations/recent?limit=50')
      if (res.ok) {
        const data = await res.json()
        for (const msg of data.messages) {
          agentStore.addMessage({
            id: msg.id,
            content: msg.content,
            role: msg.role,
            timestamp: new Date(msg.created_at),
            streaming: false,
          })
        }
      }
    } catch (e) {
      console.error('Failed to load chat history:', e)
    }
  }

  on('chat_response_chunk', handleResponseChunk)
  on('state_change', handleStateChange)
  on('mood_update', handleMoodUpdate)
  on('thought', handleThought)

  watch(status, (newStatus) => {
    agentStore.setConnected(newStatus === 'connected')
  })

  connect()
})

onUnmounted(() => {
  off('chat_response_chunk', handleResponseChunk)
  off('state_change', handleStateChange)
  off('mood_update', handleMoodUpdate)
  off('thought', handleThought)
})
</script>

<template>
  <div class="chat-view">
    <div class="status-bar">
      <span class="status-dot" :class="status" />
      <span class="status-text">{{ status }}</span>
    </div>
    <div ref="messagesContainer" class="messages">
      <div v-if="messages.length === 0" class="empty-state">
        <p>Start a conversation with CLIDE</p>
      </div>
      <ChatMessage v-for="msg in messages" :key="msg.id" :message="msg" />
    </div>
    <ChatInput :disabled="status !== 'connected' || isStreaming" @send="sendMessage" />
  </div>
</template>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.status-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--color-border, #374151);
  font-size: 12px;
  color: var(--color-text-secondary, #9ca3af);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #6b7280;
}

.status-dot.connected {
  background-color: #22c55e;
}

.status-dot.connecting {
  background-color: #eab308;
}

.status-dot.error {
  background-color: #ef4444;
}

.status-dot.disconnected {
  background-color: #6b7280;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--color-text-secondary, #6b7280);
}
</style>
