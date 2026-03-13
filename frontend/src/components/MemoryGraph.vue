<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useMemoryGraph } from '@/composables/useMemoryGraph'
import type { GraphNode } from '@/composables/useMemoryGraph'

const { graphData, loading, error, fetchGraph, searchMemories } = useMemoryGraph()

const searchQuery = ref('')
const selectedNode = ref<GraphNode | null>(null)

const nodePositions = computed(() => {
  if (!graphData.value) return new Map<string, { x: number; y: number }>()
  const positions = new Map<string, { x: number; y: number }>()
  const nodes = graphData.value.nodes
  const count = nodes.length
  if (count === 0) return positions

  // Arrange nodes in a circular layout
  const cx = 400
  const cy = 300
  const radius = Math.min(250, count * 15)
  nodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / count - Math.PI / 2
    positions.set(node.id, {
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
    })
  })
  return positions
})

function nodeRadius(node: GraphNode): number {
  return 8 + node.importance * 16
}

function nodeColor(node: GraphNode): string {
  const colors = [
    'var(--color-primary, #6366f1)',
    'var(--color-success, #22c55e)',
    'var(--color-warning, #f59e0b)',
    'var(--color-info, #3b82f6)',
    'var(--color-accent, #ec4899)',
  ]
  const tagHash = node.tags.length > 0 ? node.tags[0].length : 0
  return colors[tagHash % colors.length]
}

function selectNode(node: GraphNode) {
  selectedNode.value = selectedNode.value?.id === node.id ? null : node
}

async function handleSearch() {
  if (searchQuery.value.trim()) {
    await searchMemories(searchQuery.value.trim())
  } else {
    await fetchGraph()
  }
}

onMounted(() => {
  fetchGraph()
})
</script>

<template>
  <div class="memory-graph">
    <div class="memory-graph-header">
      <h3 class="memory-graph-title">Memory Graph</h3>
      <div class="memory-graph-search">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search memories..."
          class="memory-graph-search-input"
          @keyup.enter="handleSearch"
        />
        <button class="memory-graph-search-btn" @click="handleSearch">Search</button>
      </div>
    </div>

    <div v-if="loading" class="memory-graph-loading">Loading memories...</div>

    <div v-else-if="error" class="memory-graph-error">{{ error }}</div>

    <div v-else-if="!graphData || graphData.nodes.length === 0" class="memory-graph-empty">
      No memories yet
    </div>

    <div v-else class="memory-graph-content">
      <svg class="memory-graph-svg" viewBox="0 0 800 600" preserveAspectRatio="xMidYMid meet">
        <!-- Edges -->
        <line
          v-for="edge in graphData.edges"
          :key="`${edge.source}-${edge.target}`"
          :x1="nodePositions.get(edge.source)?.x ?? 0"
          :y1="nodePositions.get(edge.source)?.y ?? 0"
          :x2="nodePositions.get(edge.target)?.x ?? 0"
          :y2="nodePositions.get(edge.target)?.y ?? 0"
          class="memory-graph-edge"
          :stroke-opacity="edge.strength * 0.6 + 0.2"
        />

        <!-- Nodes -->
        <g
          v-for="node in graphData.nodes"
          :key="node.id"
          class="memory-graph-node"
          :transform="`translate(${nodePositions.get(node.id)?.x ?? 0}, ${nodePositions.get(node.id)?.y ?? 0})`"
          @click="selectNode(node)"
        >
          <circle
            :r="nodeRadius(node)"
            :fill="nodeColor(node)"
            :class="{ 'node-selected': selectedNode?.id === node.id }"
          />
          <text
            dy="0.35em"
            text-anchor="middle"
            class="memory-graph-node-label"
            :font-size="Math.max(8, 10 - (graphData?.nodes.length ?? 0) / 20)"
          >
            {{ node.label.substring(0, 15) }}
          </text>
        </g>
      </svg>

      <!-- Detail panel -->
      <div v-if="selectedNode" class="memory-graph-detail">
        <h4>{{ selectedNode.label }}</h4>
        <div class="detail-field">
          <span class="detail-label">Tags:</span>
          <span>{{ selectedNode.tags.join(', ') || 'None' }}</span>
        </div>
        <div class="detail-field">
          <span class="detail-label">Importance:</span>
          <span>{{ (selectedNode.importance * 100).toFixed(0) }}%</span>
        </div>
        <div class="detail-field">
          <span class="detail-label">Access count:</span>
          <span>{{ selectedNode.access_count }}</span>
        </div>
        <div class="detail-field">
          <span class="detail-label">Created:</span>
          <span>{{ new Date(selectedNode.created_at).toLocaleDateString() }}</span>
        </div>
        <button class="detail-close" @click="selectedNode = null">Close</button>
      </div>
    </div>

    <div v-if="graphData" class="memory-graph-footer">
      {{ graphData.node_count }} nodes, {{ graphData.edge_count }} edges
    </div>
  </div>
</template>

<style scoped>
.memory-graph {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: var(--color-surface, #1e1e2e);
  border-radius: 8px;
  border: 1px solid var(--color-border, #333);
  overflow: hidden;
}

.memory-graph-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border, #333);
}

.memory-graph-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text, #cdd6f4);
}

.memory-graph-search {
  display: flex;
  gap: 8px;
}

.memory-graph-search-input {
  padding: 4px 8px;
  border: 1px solid var(--color-border, #333);
  border-radius: 4px;
  background: var(--color-background, #11111b);
  color: var(--color-text, #cdd6f4);
  font-size: 12px;
}

.memory-graph-search-btn {
  padding: 4px 12px;
  border: 1px solid var(--color-border, #333);
  border-radius: 4px;
  background: var(--color-primary, #6366f1);
  color: white;
  font-size: 12px;
  cursor: pointer;
}

.memory-graph-loading,
.memory-graph-error,
.memory-graph-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  padding: 32px;
  color: var(--color-text-muted, #6c7086);
  font-size: 14px;
}

.memory-graph-error {
  color: var(--color-error, #f38ba8);
}

.memory-graph-content {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.memory-graph-svg {
  width: 100%;
  height: 100%;
}

.memory-graph-edge {
  stroke: var(--color-border, #555);
  stroke-width: 1;
}

.memory-graph-node {
  cursor: pointer;
}

.memory-graph-node circle {
  transition: stroke 0.2s;
  stroke: transparent;
  stroke-width: 2;
}

.memory-graph-node circle:hover,
.node-selected {
  stroke: var(--color-text, #cdd6f4);
  stroke-width: 3;
}

.memory-graph-node-label {
  fill: var(--color-text, #cdd6f4);
  pointer-events: none;
}

.memory-graph-detail {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 220px;
  padding: 12px;
  background: var(--color-surface, #1e1e2e);
  border: 1px solid var(--color-border, #333);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgb(0 0 0 / 30%);
}

.memory-graph-detail h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--color-text, #cdd6f4);
}

.detail-field {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  padding: 2px 0;
  color: var(--color-text-muted, #6c7086);
}

.detail-label {
  font-weight: 600;
}

.detail-close {
  margin-top: 8px;
  width: 100%;
  padding: 4px;
  border: 1px solid var(--color-border, #333);
  border-radius: 4px;
  background: transparent;
  color: var(--color-text-muted, #6c7086);
  cursor: pointer;
  font-size: 12px;
}

.memory-graph-footer {
  padding: 8px 16px;
  font-size: 11px;
  color: var(--color-text-muted, #6c7086);
  border-top: 1px solid var(--color-border, #333);
  text-align: center;
}
</style>
