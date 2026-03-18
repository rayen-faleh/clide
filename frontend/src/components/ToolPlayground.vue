<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

interface ToolDef {
  name: string
  description: string
  parameters: Record<string, unknown>
  server_name: string
}

const props = defineProps<{
  serverName: string
}>()

const emit = defineEmits<{
  close: []
}>()

const tools = ref<ToolDef[]>([])
const selectedTool = ref<ToolDef | null>(null)
const argsInput = ref('{}')
const executing = ref(false)
const result = ref<{ success: boolean; result: unknown; error: string | null } | null>(null)
const loading = ref(true)

async function loadTools() {
  loading.value = true
  try {
    const res = await fetch('/api/config/tools/definitions')
    if (res.ok) {
      const data = (await res.json()) as { servers: Record<string, ToolDef[]> }
      // Get tools for this specific server
      tools.value = data.servers[props.serverName] || []
      // Auto-select first tool
      if (tools.value.length > 0) {
        selectTool(tools.value[0])
      }
    }
  } catch (e) {
    console.error('Failed to load tools:', e)
  } finally {
    loading.value = false
  }
}

function selectTool(tool: ToolDef) {
  selectedTool.value = tool
  result.value = null
  // Pre-fill arguments from schema
  const params = tool.parameters as { properties?: Record<string, unknown> }
  if (params?.properties) {
    const defaults: Record<string, string> = {}
    for (const key of Object.keys(params.properties)) {
      defaults[key] = ''
    }
    argsInput.value = JSON.stringify(defaults, null, 2)
  } else {
    argsInput.value = '{}'
  }
}

async function executeTool() {
  if (!selectedTool.value) return
  executing.value = true
  result.value = null
  try {
    let args: Record<string, unknown> = {}
    try {
      args = JSON.parse(argsInput.value)
    } catch {
      result.value = { success: false, result: null, error: 'Invalid JSON arguments' }
      return
    }

    const res = await fetch(`/api/config/tools/${selectedTool.value.name}/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ arguments: args }),
    })
    if (res.ok) {
      result.value = await res.json()
    } else {
      const err = await res.text()
      result.value = { success: false, result: null, error: err }
    }
  } catch (e) {
    result.value = { success: false, result: null, error: String(e) }
  } finally {
    executing.value = false
  }
}

function formatResult(val: unknown): string {
  if (typeof val === 'string') return val
  return JSON.stringify(val, null, 2)
}

function renderMarkdown(text: string): string {
  const raw = marked.parse(text) as string
  return DOMPurify.sanitize(raw)
}

function handleOverlayClick(e: MouseEvent) {
  if ((e.target as HTMLElement).classList.contains('modal-overlay')) {
    emit('close')
  }
}

onMounted(() => {
  loadTools()
})
</script>

<template>
  <div class="modal-overlay" @click="handleOverlayClick">
    <div class="modal">
      <!-- Header -->
      <div class="modal-header">
        <h2 class="modal-title">Tool Playground &mdash; {{ serverName }}</h2>
        <button class="close-btn" @click="emit('close')">&times;</button>
      </div>

      <div v-if="loading" class="modal-loading">Loading tools...</div>

      <template v-else>
        <!-- Tool tabs (horizontal) -->
        <div class="tool-tabs">
          <button
            v-for="tool in tools"
            :key="tool.name"
            class="tool-tab"
            :class="{ active: selectedTool?.name === tool.name }"
            :title="tool.description"
            @click="selectTool(tool)"
          >
            {{ tool.name }}
          </button>
        </div>

        <!-- Body: left = builder, right = result -->
        <div v-if="selectedTool" class="modal-body">
          <!-- Left: query builder -->
          <div class="builder-panel">
            <div class="tool-desc">{{ selectedTool.description }}</div>

            <label class="input-label">
              Arguments (JSON)
              <textarea
                v-model="argsInput"
                rows="12"
                class="args-input"
                spellcheck="false"
                @keydown.ctrl.enter="executeTool"
                @keydown.meta.enter="executeTool"
              />
            </label>

            <div class="builder-actions">
              <button class="execute-btn" :disabled="executing" @click="executeTool">
                {{ executing ? 'Executing...' : 'Execute' }}
              </button>
              <span class="shortcut-hint">Ctrl+Enter to run</span>
            </div>
          </div>

          <!-- Right: result -->
          <div class="result-panel">
            <div v-if="!result" class="result-empty">Run a tool to see results here.</div>

            <template v-else>
              <div class="result-header" :class="{ error: !result.success }">
                {{ result.success ? 'SUCCESS' : 'ERROR' }}
              </div>
              <div class="result-body">
                <pre v-if="result.error" class="result-content error-text">{{ result.error }}</pre>
                <!-- eslint-disable-next-line vue/no-v-html -->
                <div
                  v-else-if="typeof result.result === 'string'"
                  class="result-content md-result"
                  v-html="renderMarkdown(result.result)"
                />
                <pre v-else class="result-content">{{ formatResult(result.result) }}</pre>
              </div>
            </template>
          </div>
        </div>

        <div v-else class="modal-empty">No tools available for this server.</div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: var(--color-bg-primary, #111827);
  border: 1px solid var(--color-border, #374151);
  border-radius: 12px;
  width: 90vw;
  max-width: 1100px;
  height: 80vh;
  max-height: 700px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border, #374151);
}

.modal-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text, #e5e7eb);
}

.close-btn {
  background: none;
  border: none;
  color: var(--color-text-secondary, #6b7280);
  font-size: 24px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}
.close-btn:hover {
  color: var(--color-text, #e5e7eb);
}

.modal-loading,
.modal-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary, #6b7280);
  font-size: 0.9rem;
}

/* Tool tabs */
.tool-tabs {
  display: flex;
  gap: 0;
  padding: 0 20px;
  border-bottom: 1px solid var(--color-border, #374151);
  overflow-x: auto;
}

.tool-tab {
  padding: 10px 16px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--color-text-secondary, #9ca3af);
  font-size: 0.8rem;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}
.tool-tab:hover {
  color: var(--color-text, #e5e7eb);
  background: rgba(255, 255, 255, 0.03);
}
.tool-tab.active {
  color: #60a5fa;
  border-bottom-color: #60a5fa;
}

/* Body: two panels */
.modal-body {
  display: flex;
  flex: 1;
  min-height: 0;
}

.builder-panel {
  width: 45%;
  padding: 16px 20px;
  border-right: 1px solid var(--color-border, #374151);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.tool-desc {
  font-size: 0.8rem;
  color: var(--color-text-secondary, #9ca3af);
  margin-bottom: 12px;
  line-height: 1.4;
}

.input-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.75rem;
  color: var(--color-text-secondary, #9ca3af);
  flex: 1;
}

.args-input {
  flex: 1;
  min-height: 120px;
  background: var(--color-surface, #1f2937);
  border: 1px solid var(--color-border, #374151);
  border-radius: 6px;
  color: var(--color-text, #e5e7eb);
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 0.8rem;
  padding: 10px;
  resize: none;
}
.args-input:focus {
  outline: none;
  border-color: var(--color-focus, #2563eb);
}

.builder-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
}

.execute-btn {
  padding: 8px 24px;
  background: rgba(34, 197, 94, 0.15);
  border: 1px solid #22c55e;
  border-radius: 6px;
  color: #4ade80;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}
.execute-btn:hover:not(:disabled) {
  background: rgba(34, 197, 94, 0.3);
}
.execute-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.shortcut-hint {
  font-size: 0.7rem;
  color: var(--color-text-secondary, #6b7280);
}

/* Result panel */
.result-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.result-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary, #6b7280);
  font-size: 0.85rem;
}

.result-header {
  padding: 8px 20px;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  background: rgba(34, 197, 94, 0.08);
  color: #4ade80;
  border-bottom: 1px solid rgba(34, 197, 94, 0.2);
}
.result-header.error {
  background: rgba(239, 68, 68, 0.08);
  color: #f87171;
  border-bottom-color: rgba(239, 68, 68, 0.2);
}

.result-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

.result-content {
  margin: 0;
  font-size: 0.8rem;
  color: var(--color-text, #e5e7eb);
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'SF Mono', 'Fira Code', monospace;
  line-height: 1.5;
}

.error-text {
  color: #f87171;
}

.md-result {
  font-family: inherit;
}
.md-result :deep(p) {
  margin: 0 0 0.5em;
}
.md-result :deep(p:last-child) {
  margin-bottom: 0;
}
.md-result :deep(code) {
  background: rgba(0, 0, 0, 0.2);
  padding: 1px 4px;
  border-radius: 3px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 0.9em;
}
.md-result :deep(pre) {
  background: rgba(0, 0, 0, 0.3);
  padding: 8px 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.5em 0;
}
.md-result :deep(strong) {
  font-weight: 700;
}
</style>
