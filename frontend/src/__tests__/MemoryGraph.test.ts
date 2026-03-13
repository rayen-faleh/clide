// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, readonly } from 'vue'
import MemoryGraph from '@/components/MemoryGraph.vue'

// Mock the composable
const mockFetchGraph = vi.fn()
const mockSearchMemories = vi.fn()

const mockGraphData = ref<null | {
  nodes: Array<{
    id: string
    label: string
    importance: number
    access_count: number
    tags: string[]
    created_at: string
  }>
  edges: Array<{ source: string; target: string; relationship: string; strength: number }>
  node_count: number
  edge_count: number
}>(null)
const mockLoading = ref(false)
const mockError = ref<string | null>(null)

vi.mock('@/composables/useMemoryGraph', () => ({
  useMemoryGraph: () => ({
    graphData: readonly(mockGraphData),
    loading: readonly(mockLoading),
    error: readonly(mockError),
    fetchGraph: mockFetchGraph,
    searchMemories: mockSearchMemories,
  }),
}))

beforeEach(() => {
  mockGraphData.value = null
  mockLoading.value = false
  mockError.value = null
  vi.clearAllMocks()
})

describe('MemoryGraph', () => {
  it('renders loading state', () => {
    mockLoading.value = true
    const wrapper = mount(MemoryGraph)
    expect(wrapper.text()).toContain('Loading memories...')
  })

  it('renders empty state', () => {
    mockGraphData.value = null
    mockLoading.value = false
    const wrapper = mount(MemoryGraph)
    expect(wrapper.text()).toContain('No memories yet')
  })

  it('renders nodes', () => {
    mockGraphData.value = {
      nodes: [
        {
          id: 'z1',
          label: 'Test memory',
          importance: 0.8,
          access_count: 3,
          tags: ['test'],
          created_at: '2025-01-01T00:00:00Z',
        },
        {
          id: 'z2',
          label: 'Another memory',
          importance: 0.5,
          access_count: 1,
          tags: ['other'],
          created_at: '2025-01-02T00:00:00Z',
        },
      ],
      edges: [],
      node_count: 2,
      edge_count: 0,
    }
    const wrapper = mount(MemoryGraph)
    expect(wrapper.text()).toContain('Test memory')
    expect(wrapper.text()).toContain('Another memory')
    expect(wrapper.text()).toContain('2 nodes, 0 edges')
  })

  it('renders search input', () => {
    const wrapper = mount(MemoryGraph)
    const input = wrapper.find('.memory-graph-search-input')
    expect(input.exists()).toBe(true)
    expect(input.attributes('placeholder')).toBe('Search memories...')
  })

  it('calls fetchGraph on mount', () => {
    mount(MemoryGraph)
    expect(mockFetchGraph).toHaveBeenCalled()
  })
})
