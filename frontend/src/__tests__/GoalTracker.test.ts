// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import GoalTracker from '@/components/GoalTracker.vue'

interface Goal {
  description: string
  priority: string
  status: string
  progress: number
}

function createGoal(overrides: Partial<Goal> = {}): Goal {
  return {
    description: 'Test goal',
    priority: 'medium',
    status: 'active',
    progress: 0.0,
    ...overrides,
  }
}

describe('GoalTracker', () => {
  it('renders goals', () => {
    const goals = [
      createGoal({ description: 'Learn Vue' }),
      createGoal({ description: 'Build project' }),
    ]
    const wrapper = mount(GoalTracker, {
      props: { goals },
    })

    expect(wrapper.text()).toContain('Learn Vue')
    expect(wrapper.text()).toContain('Build project')
  })

  it('renders empty state when no goals', () => {
    const wrapper = mount(GoalTracker, {
      props: { goals: [] },
    })

    expect(wrapper.text()).toContain('No goals yet')
  })

  it('shows progress', () => {
    const goals = [createGoal({ description: 'Half done', progress: 0.5 })]
    const wrapper = mount(GoalTracker, {
      props: { goals },
    })

    const progressBar = wrapper.find('.goal-progress-fill')
    expect(progressBar.exists()).toBe(true)
  })
})
