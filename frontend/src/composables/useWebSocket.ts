import { ref, readonly } from 'vue'
import type { WSMessage } from '@/types/messages'

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

function defaultWsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws`
}

export function useWebSocket(url: string = defaultWsUrl()) {
  const status = ref<ConnectionStatus>('disconnected')
  const lastMessage = ref<WSMessage | null>(null)
  const error = ref<string | null>(null)
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  const messageHandlers = new Map<string, ((msg: WSMessage) => void)[]>()

  function connect() {
    if (ws?.readyState === WebSocket.OPEN) return

    status.value = 'connecting'
    ws = new WebSocket(url)

    ws.onopen = () => {
      status.value = 'connected'
      error.value = null
    }

    ws.onmessage = (event: MessageEvent) => {
      try {
        const msg: WSMessage = JSON.parse(event.data as string)
        lastMessage.value = msg

        // Call type-specific handlers
        const handlers = messageHandlers.get(msg.type)
        if (handlers) {
          handlers.forEach((handler) => handler(msg))
        }

        // Call wildcard handlers
        const wildcardHandlers = messageHandlers.get('*')
        if (wildcardHandlers) {
          wildcardHandlers.forEach((handler) => handler(msg))
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e)
      }
    }

    ws.onerror = () => {
      status.value = 'error'
      error.value = 'WebSocket connection error'
    }

    ws.onclose = () => {
      status.value = 'disconnected'
      scheduleReconnect()
    }
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    ws?.close()
    ws = null
    status.value = 'disconnected'
  }

  function send(message: WSMessage) {
    if (ws?.readyState !== WebSocket.OPEN) {
      error.value = 'WebSocket is not connected'
      return
    }
    ws.send(JSON.stringify(message))
  }

  function on(type: string, handler: (msg: WSMessage) => void) {
    if (!messageHandlers.has(type)) {
      messageHandlers.set(type, [])
    }
    messageHandlers.get(type)!.push(handler)
  }

  function off(type: string, handler: (msg: WSMessage) => void) {
    const handlers = messageHandlers.get(type)
    if (handlers) {
      const index = handlers.indexOf(handler)
      if (index > -1) handlers.splice(index, 1)
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer) return
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, 3000)
  }

  return {
    status: readonly(status),
    lastMessage: readonly(lastMessage),
    error: readonly(error),
    connect,
    disconnect,
    send,
    on,
    off,
  }
}
