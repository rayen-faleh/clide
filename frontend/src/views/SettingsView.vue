<script setup lang="ts">
import { ref, onMounted } from 'vue'
import AgentConfig from '@/components/AgentConfig.vue'
import ToolStatus from '@/components/ToolStatus.vue'
import ToolPlayground from '@/components/ToolPlayground.vue'

interface Tool {
  name: string
  description: string
  enabled: boolean
  status: string
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const config = ref<Record<string, any> | null>(null)
const tools = ref<Tool[]>([])
const loading = ref(true)
const saving = ref(false)
const toast = ref<{ message: string; type: 'success' | 'error' } | null>(null)
const editingSkill = ref<string | null>(null)
const skillContent = ref('')
const playgroundServer = ref<string | null>(null)

async function fetchConfig() {
  try {
    const res = await fetch('/api/config')
    if (!res.ok) throw new Error('Failed to fetch config')
    config.value = await res.json()
  } catch (err) {
    showToast('Failed to load configuration', 'error')
    console.error(err)
  }
}

async function fetchToolsStatus() {
  try {
    const res = await fetch('/api/config/tools/status')
    if (!res.ok) throw new Error('Failed to fetch tools status')
    const data = await res.json()
    tools.value = data.tools
  } catch (err) {
    console.error(err)
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function handleSave(updated: Record<string, any>) {
  saving.value = true
  try {
    const res = await fetch('/api/config', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updated),
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || 'Failed to save')
    }
    config.value = await res.json()
    showToast('Configuration saved', 'success')
  } catch (err) {
    showToast(err instanceof Error ? err.message : 'Save failed', 'error')
  } finally {
    saving.value = false
  }
}

function showToast(message: string, type: 'success' | 'error') {
  toast.value = { message, type }
  setTimeout(() => {
    toast.value = null
  }, 3000)
}

async function loadSkill(toolName: string) {
  try {
    const res = await fetch(`/api/config/tools/${toolName}/skill`)
    if (res.ok) {
      const data = await res.json()
      skillContent.value = data.content || ''
    }
  } catch (err) {
    console.error(err)
  }
  editingSkill.value = toolName
}

async function saveSkill() {
  if (!editingSkill.value) return
  try {
    await fetch(`/api/config/tools/${editingSkill.value}/skill`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: skillContent.value }),
    })
    // Also cache in localStorage
    const cached = JSON.parse(localStorage.getItem('clide_tool_skills') || '{}')
    cached[editingSkill.value] = skillContent.value
    localStorage.setItem('clide_tool_skills', JSON.stringify(cached))

    showToast('Skill saved', 'success')
    editingSkill.value = null
    skillContent.value = ''
  } catch (err) {
    showToast('Failed to save skill', 'error')
    console.error(err)
  }
}

function cancelSkillEdit() {
  editingSkill.value = null
  skillContent.value = ''
}

onMounted(async () => {
  await Promise.all([fetchConfig(), fetchToolsStatus()])
  loading.value = false
})
</script>

<template>
  <div class="settings-view">
    <div v-if="toast" class="toast" :class="toast.type">
      {{ toast.message }}
    </div>

    <div v-if="loading" class="loading">Loading configuration...</div>

    <template v-else>
      <div class="settings-header">
        <h2 class="page-title">Settings</h2>
        <p v-if="config" class="agent-name">Agent: {{ config.agent?.name }}</p>
      </div>

      <div class="settings-body">
        <div class="settings-main">
          <section class="config-section">
            <h3 class="section-title">LLM Configuration</h3>
            <div class="info-row">
              <span class="info-label">Provider</span>
              <span class="info-value">{{ config?.agent?.llm?.provider }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Model</span>
              <span class="info-value">{{ config?.agent?.llm?.model }}</span>
            </div>
          </section>

          <AgentConfig v-if="config" :config="config" @save="handleSave" />
        </div>

        <div class="settings-sidebar">
          <section class="config-section">
            <h3 class="section-title">Tool Status</h3>
            <ToolStatus
              :tools="tools"
              @edit-skill="loadSkill"
              @open-playground="(name: string) => (playgroundServer = name)"
            />
          </section>

          <!-- Skill Editor (shown when editing) -->
          <section v-if="editingSkill" class="config-section skill-editor">
            <h3 class="section-title">Skill: {{ editingSkill }}</h3>
            <p class="skill-hint">
              Describe how this tool should be used. The agent will see these instructions in its
              system prompt.
            </p>
            <textarea
              v-model="skillContent"
              rows="10"
              placeholder="Write instructions for how to use this tool..."
              class="skill-textarea"
            ></textarea>
            <div class="skill-actions">
              <button class="save-btn" @click="saveSkill">Save</button>
              <button class="cancel-btn" @click="cancelSkillEdit">Cancel</button>
            </div>
          </section>
        </div>
      </div>
    </template>

    <div v-if="saving" class="saving-overlay">Saving...</div>

    <!-- Tool Playground Modal -->
    <ToolPlayground
      v-if="playgroundServer"
      :server-name="playgroundServer"
      @close="playgroundServer = null"
    />
  </div>
</template>

<style scoped>
.settings-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
  gap: 16px;
  overflow-y: auto;
  position: relative;
}

.settings-header {
  display: flex;
  align-items: baseline;
  gap: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text);
}

.agent-name {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.settings-body {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 16px;
  flex: 1;
}

.settings-main {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.settings-sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.config-section {
  background-color: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 16px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.info-label {
  width: 80px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.info-value {
  font-size: 13px;
  color: var(--color-text);
  font-family: 'SF Mono', 'Fira Code', monospace;
}

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.toast {
  position: fixed;
  top: 60px;
  right: 16px;
  padding: 10px 16px;
  border-radius: 6px;
  font-size: 13px;
  z-index: 100;
  animation: slideIn 0.2s ease-out;
}

.toast.success {
  background-color: #166534;
  color: #bbf7d0;
  border: 1px solid #22c55e;
}

.toast.error {
  background-color: #7f1d1d;
  color: #fecaca;
  border: 1px solid #ef4444;
}

.saving-overlay {
  position: fixed;
  bottom: 16px;
  right: 16px;
  padding: 8px 14px;
  background-color: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

@keyframes slideIn {
  from {
    transform: translateX(20px);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

.skill-editor {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.skill-hint {
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.4;
}

.skill-textarea {
  width: 100%;
  padding: 8px 10px;
  background-color: var(--color-input-bg);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text);
  font-size: 13px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  outline: none;
  resize: vertical;
}

.skill-textarea:focus {
  border-color: var(--color-focus);
}

.skill-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.save-btn {
  padding: 6px 16px;
  background-color: var(--color-button);
  color: var(--color-user-text);
  border: none;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.15s;
}

.save-btn:hover {
  background-color: var(--color-button-hover);
}

.cancel-btn {
  padding: 6px 16px;
  background-color: transparent;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  transition:
    background-color 0.15s,
    color 0.15s;
}

.cancel-btn:hover {
  background-color: var(--color-surface);
  color: var(--color-text);
}

@media (max-width: 768px) {
  .settings-body {
    grid-template-columns: 1fr;
  }
}
</style>
