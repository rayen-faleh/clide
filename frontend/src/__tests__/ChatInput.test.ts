// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatInput from '@/components/ChatInput.vue'

describe('ChatInput', () => {
  it('renders input and send button', () => {
    const wrapper = mount(ChatInput)

    expect(wrapper.find('textarea').exists()).toBe(true)
    expect(wrapper.find('button').exists()).toBe(true)
  })

  it('emits send event with content on button click', async () => {
    const wrapper = mount(ChatInput)

    const textarea = wrapper.find('textarea')
    await textarea.setValue('Hello world')
    await wrapper.find('button').trigger('click')

    expect(wrapper.emitted('send')).toBeTruthy()
    expect(wrapper.emitted('send')![0]).toEqual(['Hello world'])
  })

  it('clears input after send', async () => {
    const wrapper = mount(ChatInput)

    const textarea = wrapper.find('textarea')
    await textarea.setValue('Hello world')
    await wrapper.find('button').trigger('click')

    expect((textarea.element as HTMLTextAreaElement).value).toBe('')
  })

  it('disables when disabled prop is true', () => {
    const wrapper = mount(ChatInput, {
      props: { disabled: true },
    })

    expect((wrapper.find('textarea').element as HTMLTextAreaElement).disabled).toBe(true)
    expect((wrapper.find('button').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('does not emit send for empty input', async () => {
    const wrapper = mount(ChatInput)

    await wrapper.find('button').trigger('click')

    expect(wrapper.emitted('send')).toBeFalsy()
  })

  it('sends on Enter key (without Shift)', async () => {
    const wrapper = mount(ChatInput)

    const textarea = wrapper.find('textarea')
    await textarea.setValue('Hello')
    await textarea.trigger('keydown', { key: 'Enter', shiftKey: false })

    expect(wrapper.emitted('send')).toBeTruthy()
    expect(wrapper.emitted('send')![0]).toEqual(['Hello'])
  })

  it('does not send on Shift+Enter', async () => {
    const wrapper = mount(ChatInput)

    const textarea = wrapper.find('textarea')
    await textarea.setValue('Hello')
    await textarea.trigger('keydown', { key: 'Enter', shiftKey: true })

    expect(wrapper.emitted('send')).toBeFalsy()
  })
})
