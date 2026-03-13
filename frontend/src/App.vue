<script setup lang="ts"></script>

<template>
  <div id="app">
    <nav class="navbar">
      <div class="nav-brand">CLIDE</div>
      <div class="nav-links">
        <RouterLink to="/chat">Chat</RouterLink>
        <RouterLink to="/dashboard">Dashboard</RouterLink>
      </div>
    </nav>
    <main class="main-content">
      <RouterView />
    </main>
  </div>
</template>

<style>
:root {
  --color-bg: #111827;
  --color-surface: #1f2937;
  --color-border: #374151;
  --color-text: #e5e7eb;
  --color-text-secondary: #9ca3af;
  --color-user-bubble: #2563eb;
  --color-user-text: #ffffff;
  --color-assistant-bubble: #374151;
  --color-assistant-text: #e5e7eb;
  --color-button: #2563eb;
  --color-button-hover: #1d4ed8;
  --color-focus: #2563eb;
  --color-input-bg: #1f2937;
  --color-textarea-bg: #111827;
  --color-streaming: #9ca3af;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background-color: var(--color-bg);
  color: var(--color-text);
}

code,
pre {
  font-family: 'SF Mono', 'Fira Code', 'Fira Mono', Menlo, monospace;
}

#app {
  display: flex;
  flex-direction: column;
  height: 100vh;
}
</style>

<style scoped>
.navbar {
  display: flex;
  align-items: center;
  padding: 0 16px;
  height: 48px;
  background-color: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
}

.nav-brand {
  font-weight: 700;
  font-size: 18px;
  margin-right: 24px;
  letter-spacing: 0.05em;
}

.nav-links {
  display: flex;
  gap: 16px;
}

.nav-links a {
  color: var(--color-text-secondary);
  text-decoration: none;
  font-size: 14px;
  padding: 4px 8px;
  border-radius: 4px;
  transition: color 0.15s;
}

.nav-links a:hover,
.nav-links a.router-link-active {
  color: var(--color-text);
}

.main-content {
  flex: 1;
  min-height: 0;
}
</style>
