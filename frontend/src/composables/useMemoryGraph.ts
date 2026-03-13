import { ref, readonly } from 'vue'

export interface GraphNode {
  id: string
  label: string
  importance: number
  access_count: number
  tags: string[]
  created_at: string
}

export interface GraphEdge {
  source: string
  target: string
  relationship: string
  strength: number
}

export interface MemoryGraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  node_count: number
  edge_count: number
}

export function useMemoryGraph(baseUrl: string = 'http://localhost:8000') {
  const graphData = ref<MemoryGraphData | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchGraph(limit: number = 100) {
    loading.value = true
    error.value = null
    try {
      const response = await fetch(`${baseUrl}/api/memories/graph?limit=${limit}`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      graphData.value = await response.json()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
    } finally {
      loading.value = false
    }
  }

  async function searchMemories(query: string, limit: number = 10) {
    loading.value = true
    error.value = null
    try {
      const response = await fetch(
        `${baseUrl}/api/memories/search?q=${encodeURIComponent(query)}&limit=${limit}`,
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return await response.json()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    graphData: readonly(graphData),
    loading: readonly(loading),
    error: readonly(error),
    fetchGraph,
    searchMemories,
  }
}
