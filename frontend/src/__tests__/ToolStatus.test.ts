// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ToolStatus from '@/components/ToolStatus.vue'

interface Tool {
  name: string
  description: string
  enabled: boolean
  status: string
}

function createTool(overrides: Partial<Tool> = {}): Tool {
  return {
    name: 'web_search',
    description: 'Search the web',
    enabled: true,
    status: 'available',
    ...overrides,
  }
}

describe('ToolStatus', () => {
  it('renders tool list', () => {
    const tools = [
      createTool({ name: 'web_search', description: 'Search the web' }),
      createTool({ name: 'file_reader', description: 'Read files' }),
    ]
    const wrapper = mount(ToolStatus, {
      props: { tools },
    })

    expect(wrapper.text()).toContain('web_search')
    expect(wrapper.text()).toContain('file_reader')
    expect(wrapper.text()).toContain('Search the web')
    expect(wrapper.text()).toContain('Read files')
  })

  it('renders empty state when no tools', () => {
    const wrapper = mount(ToolStatus, {
      props: { tools: [] },
    })

    expect(wrapper.text()).toContain('No tools configured')
  })

  it('shows status indicator for available tool', () => {
    const tools = [createTool({ status: 'available' })]
    const wrapper = mount(ToolStatus, {
      props: { tools },
    })

    const indicator = wrapper.find('.status-dot')
    expect(indicator.exists()).toBe(true)
    expect(indicator.classes()).toContain('available')
  })

  it('shows status indicator for disabled tool', () => {
    const tools = [createTool({ status: 'disabled', enabled: false })]
    const wrapper = mount(ToolStatus, {
      props: { tools },
    })

    const indicator = wrapper.find('.status-dot')
    expect(indicator.exists()).toBe(true)
    expect(indicator.classes()).toContain('disabled')
  })

  it('shows status indicator for error tool', () => {
    const tools = [createTool({ status: 'error' })]
    const wrapper = mount(ToolStatus, {
      props: { tools },
    })

    const indicator = wrapper.find('.status-dot')
    expect(indicator.exists()).toBe(true)
    expect(indicator.classes()).toContain('error')
  })
})
