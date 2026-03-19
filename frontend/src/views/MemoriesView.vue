<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

interface MemoryItem {
  id: string
  content: string
  summary: string
  importance: number
  created_at: string
  metadata: Record<string, string>
}

const jsonInput = ref('')
const uploading = ref(false)
const toast = ref<{ message: string; type: 'success' | 'error' } | null>(null)
const recentMemories = ref<MemoryItem[]>([])
const showPrompt = ref(false)

const parsedCount = computed(() => {
  try {
    const data = JSON.parse(jsonInput.value)
    if (Array.isArray(data)) return data.length
    return 0
  } catch {
    return -1
  }
})

const isValid = computed(() => parsedCount.value > 0)

function showToast(message: string, type: 'success' | 'error') {
  toast.value = { message, type }
  setTimeout(() => {
    toast.value = null
  }, 3000)
}

async function uploadMemories() {
  if (!isValid.value) return
  uploading.value = true
  try {
    const memories = JSON.parse(jsonInput.value)
    const res = await fetch('/api/memories/upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ memories }),
    })
    if (res.ok) {
      const data = await res.json()
      showToast(`Uploaded ${data.created} memories`, 'success')
      jsonInput.value = ''
      await fetchRecent()
    } else {
      const err = await res.text()
      showToast(`Upload failed: ${err}`, 'error')
    }
  } catch (e) {
    showToast(`Error: ${e}`, 'error')
  } finally {
    uploading.value = false
  }
}

async function fetchRecent() {
  try {
    const res = await fetch('/api/memories?limit=20')
    if (res.ok) {
      const data = await res.json()
      recentMemories.value = data.memories
    }
  } catch (e) {
    console.error('Failed to load memories:', e)
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const llmPrompt = `You are helping create synthetic memories for an AI agent character.
Given the following character description and source material, generate
a JSON array of first-person memories as if the character experienced
these events. Each memory should feel authentic, emotional, and specific.

Character: [paste your agent's system prompt here]

Source material: [paste data, backstory, or topics you want the agent to remember]

Generate 10-20 memories in this JSON format:
[
  {
    "content": "First-person narration of the memory (2-5 sentences). Include sensory details, emotions, and specific moments.",
    "summary": "One-line description",
    "keywords": ["relevant", "keywords"],
    "tags": ["experience" or "knowledge" or "opinion" or "observation"],
    "importance": 0.0-1.0,
    "timestamp": "ISO 8601 datetime (fabricate a believable date)"
  }
]

Rules:
- Write in first person as the character
- Include emotional texture (not just facts)
- Vary importance (not everything is 0.9)
- Mix mundane and significant memories
- Use the character's voice and vocabulary
- Make timestamps span different dates to feel natural`

onMounted(fetchRecent)
</script>

<template>
  <div class="memories-view">
    <div v-if="toast" class="toast" :class="toast.type">{{ toast.message }}</div>

    <h2 class="page-title">Memory Upload</h2>

    <!-- How-To Section -->
    <section class="info-section">
      <h3 class="section-title">How To</h3>
      <p class="info-text">
        Upload fabricated memories to give your agent a backstory and diverse experiences. Memories
        should be written in <strong>first person</strong>, as if the agent lived through them. They
        will be stored directly and recalled naturally during thinking and conversations.
      </p>

      <div class="format-example">
        <h4>JSON Format</h4>
        <pre class="code-block">
[
  {
    "content": "I remember the first time I saw a neural network hallucinate. It was 3AM, the lab was empty, and the model started generating faces that didn't exist. Beautiful, haunting faces.",
    "summary": "First encounter with AI hallucinations",
    "keywords": ["AI", "hallucination", "neural network", "lab"],
    "tags": ["experience"],
    "importance": 0.7,
    "timestamp": "2025-06-15T03:42:00Z"
  }
]</pre
        >
      </div>

      <div class="fields-list">
        <h4>Fields</h4>
        <ul>
          <li><strong>content</strong> (required) — The memory text, first person narration</li>
          <li><strong>summary</strong> — One-line description for quick reference</li>
          <li><strong>keywords</strong> — Search terms for semantic recall</li>
          <li><strong>tags</strong> — Categories (experience, knowledge, opinion, observation)</li>
          <li><strong>importance</strong> — 0.0 to 1.0 (default 0.5)</li>
          <li><strong>timestamp</strong> — Fabricated date in ISO 8601 format</li>
        </ul>
      </div>

      <div class="prompt-section">
        <button class="prompt-toggle" @click="showPrompt = !showPrompt">
          {{ showPrompt ? 'Hide' : 'Show' }} LLM prompt for generating memories
        </button>
        <div v-if="showPrompt" class="prompt-content">
          <p class="prompt-hint">
            Copy this prompt and paste it into any LLM (Claude, ChatGPT, etc.) along with your
            agent's system prompt and source material to generate memories:
          </p>
          <pre class="code-block prompt-block">{{ llmPrompt }}</pre>
        </div>
      </div>
    </section>

    <!-- Upload Section -->
    <section class="upload-section">
      <h3 class="section-title">Upload</h3>
      <textarea
        v-model="jsonInput"
        class="json-input"
        rows="12"
        placeholder="Paste your JSON array of memories here..."
        spellcheck="false"
      />
      <div class="upload-footer">
        <span class="parse-status" :class="{ valid: isValid, invalid: parsedCount === -1 }">
          {{
            parsedCount === -1
              ? 'Invalid JSON'
              : parsedCount === 0
                ? 'No memories'
                : `${parsedCount} memor${parsedCount === 1 ? 'y' : 'ies'}`
          }}
        </span>
        <button class="upload-btn" :disabled="!isValid || uploading" @click="uploadMemories">
          {{ uploading ? 'Uploading...' : 'Upload' }}
        </button>
      </div>
    </section>

    <!-- Recent Memories -->
    <section class="recent-section">
      <h3 class="section-title">Recent Memories ({{ recentMemories.length }})</h3>
      <div v-if="recentMemories.length === 0" class="empty-state">No memories stored yet.</div>
      <div v-else class="memory-list">
        <div v-for="mem in recentMemories" :key="mem.id" class="memory-item">
          <div class="memory-header">
            <span class="memory-date">{{ formatDate(mem.created_at) }}</span>
            <span class="memory-importance" :style="{ opacity: 0.4 + mem.importance * 0.6 }">
              {{ mem.importance.toFixed(1) }}
            </span>
            <span v-if="mem.metadata?.type === 'uploaded_memory'" class="memory-badge uploaded">
              uploaded
            </span>
            <span v-else-if="mem.metadata?.type" class="memory-badge">
              {{ mem.metadata.type }}
            </span>
          </div>
          <p class="memory-content">
            {{ mem.summary || mem.content.slice(0, 150) + (mem.content.length > 150 ? '...' : '') }}
          </p>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.memories-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 16px;
  overflow-y: auto;
  height: 100%;
  position: relative;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text, #e5e7eb);
  margin: 0;
}

.toast {
  position: fixed;
  top: 16px;
  right: 16px;
  padding: 10px 20px;
  border-radius: 6px;
  font-size: 0.85rem;
  z-index: 1000;
}
.toast.success {
  background: rgba(34, 197, 94, 0.15);
  border: 1px solid #22c55e;
  color: #4ade80;
}
.toast.error {
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid #ef4444;
  color: #f87171;
}

.info-section,
.upload-section,
.recent-section {
  background: var(--color-surface, #1f2937);
  border: 1px solid var(--color-border, #374151);
  border-radius: 8px;
  padding: 16px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text, #e5e7eb);
  margin: 0 0 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.info-text {
  font-size: 0.85rem;
  color: var(--color-text-secondary, #9ca3af);
  line-height: 1.5;
  margin: 0 0 16px;
}

.format-example h4,
.fields-list h4 {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-text, #e5e7eb);
  margin: 12px 0 6px;
}

.code-block {
  background: var(--color-bg-primary, #111827);
  border: 1px solid var(--color-border, #374151);
  border-radius: 6px;
  padding: 12px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 0.75rem;
  color: var(--color-text, #e5e7eb);
  overflow-x: auto;
  white-space: pre;
  margin: 0;
}

.fields-list ul {
  margin: 0;
  padding-left: 20px;
  font-size: 0.8rem;
  color: var(--color-text-secondary, #9ca3af);
  line-height: 1.8;
}

.prompt-section {
  margin-top: 12px;
}

.prompt-toggle {
  background: none;
  border: none;
  color: #60a5fa;
  font-size: 0.8rem;
  cursor: pointer;
  padding: 0;
  text-decoration: underline;
}

.prompt-content {
  margin-top: 8px;
}

.prompt-hint {
  font-size: 0.8rem;
  color: var(--color-text-secondary, #9ca3af);
  margin: 0 0 8px;
}

.prompt-block {
  white-space: pre-wrap;
  font-size: 0.7rem;
  max-height: 300px;
  overflow-y: auto;
}

.json-input {
  width: 100%;
  background: var(--color-bg-primary, #111827);
  border: 1px solid var(--color-border, #374151);
  border-radius: 6px;
  color: var(--color-text, #e5e7eb);
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 0.8rem;
  padding: 12px;
  resize: vertical;
}
.json-input:focus {
  outline: none;
  border-color: var(--color-focus, #2563eb);
}

.upload-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 8px;
}

.parse-status {
  font-size: 0.75rem;
  color: var(--color-text-secondary, #6b7280);
}
.parse-status.valid {
  color: #4ade80;
}
.parse-status.invalid {
  color: #f87171;
}

.upload-btn {
  padding: 8px 24px;
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid #3b82f6;
  border-radius: 6px;
  color: #60a5fa;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}
.upload-btn:hover:not(:disabled) {
  background: rgba(59, 130, 246, 0.3);
}
.upload-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.empty-state {
  color: var(--color-text-secondary, #6b7280);
  font-size: 0.85rem;
  text-align: center;
  padding: 16px;
}

.memory-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 400px;
  overflow-y: auto;
}

.memory-item {
  padding: 10px 12px;
  background: var(--color-bg-primary, #111827);
  border: 1px solid var(--color-border, #374151);
  border-radius: 6px;
}

.memory-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.memory-date {
  font-size: 0.7rem;
  color: var(--color-text-secondary, #6b7280);
}

.memory-importance {
  font-size: 0.65rem;
  font-weight: 600;
  color: #facc15;
}

.memory-badge {
  font-size: 0.6rem;
  padding: 1px 6px;
  border-radius: 3px;
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.5px;
  background: rgba(100, 100, 100, 0.2);
  color: #9ca3af;
}
.memory-badge.uploaded {
  background: rgba(139, 92, 246, 0.2);
  color: #a78bfa;
}

.memory-content {
  font-size: 0.8rem;
  color: var(--color-text, #e5e7eb);
  line-height: 1.4;
  margin: 0;
}
</style>
