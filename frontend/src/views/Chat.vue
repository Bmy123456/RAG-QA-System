<template>
  <div class="chat-layout">
    <aside class="chat-sidebar">
      <router-link to="/" class="back-link">&larr; 返回知识库</router-link>
      <div class="conv-list">
        <div v-for="c in conversations" :key="c.id" class="conv-item" @click="loadConversation(c.id)">
          {{ c.title }}
        </div>
        <button @click="newChat" class="new-chat-btn">+ 新对话</button>
      </div>
    </aside>
    <main class="chat-main">
      <div class="messages" ref="msgContainer">
        <div v-for="(msg, i) in messages" :key="i" :class="['message', msg.role]">
          <div class="content" v-html="renderContent(msg.content)"></div>
          <div v-if="msg.sources" class="sources">
            <div v-for="s in msg.sources" :key="s.index" class="source-tag">
              [{{ s.index }}] {{ s.filename }}{{ s.page ? ' P' + s.page : '' }}
            </div>
          </div>
        </div>
      </div>
      <div class="input-area">
        <textarea v-model="question" @keydown.enter.exact.prevent="send" placeholder="输入问题..." rows="2"></textarea>
        <button @click="send" :disabled="streaming">发送</button>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'
import { marked } from 'marked'

const route = useRoute()
const kbId = route.params.kbId
const messages = ref([])
const conversations = ref([])
const question = ref('')
const streaming = ref(false)
const convId = ref(null)
const msgContainer = ref(null)

onMounted(async () => {
  conversations.value = (await api.get(`/chat/conversations/${kbId}`)).data
})

function renderContent(text) {
  return marked(text || '', { breaks: true })
}

async function send() {
  if (!question.value.trim()) return
  const q = question.value
  question.value = ''
  messages.value.push({ role: 'user', content: q })
  messages.value.push({ role: 'assistant', content: '', sources: null })
  streaming.value = true

  const response = await fetch(`/api/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` },
    body: JSON.stringify({ kb_id: parseInt(kbId), question: q, conversation_id: convId.value }),
  })

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  const lastMsg = messages.value[messages.value.length - 1]

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    const text = decoder.decode(value)
    for (const line of text.split('\n')) {
      if (line.startsWith('data: ') && line !== 'data: [DONE]') {
        lastMsg.content += line.slice(6)
      }
    }
    await nextTick()
    msgContainer.value?.scrollTo(0, msgContainer.value.scrollHeight)
  }
  streaming.value = false

  if (!convId.value) {
    conversations.value = (await api.get(`/chat/conversations/${kbId}`)).data
    if (conversations.value.length > 0) convId.value = conversations.value[0].id
  }
}

async function newChat() {
  convId.value = null
  messages.value = []
}

async function loadConversation(id) {
  convId.value = id
  const msgs = (await api.get(`/chat/messages/${id}`)).data
  messages.value = msgs.map(m => ({ role: m.role, content: m.content, sources: m.sources }))
}
</script>

<style scoped>
.chat-layout { display: flex; height: 100vh; }
.chat-sidebar { width: 240px; background: #1e1e2e; color: #cdd6f4; padding: 1rem; }
.chat-sidebar a { color: #89b4fa; text-decoration: none; display: block; margin-bottom: 1rem; }
.conv-list { display: flex; flex-direction: column; gap: 0.3rem; }
.conv-item { padding: 0.5rem; cursor: pointer; border-radius: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conv-item:hover { background: #313244; }
.new-chat-btn { background: #4f46e5; color: white; border: none; padding: 0.5rem; border-radius: 4px; cursor: pointer; margin-top: 0.5rem; }
.chat-main { flex: 1; display: flex; flex-direction: column; }
.messages { flex: 1; overflow-y: auto; padding: 1rem 2rem; }
.message { margin-bottom: 1rem; }
.message.user .content { background: #4f46e5; color: white; padding: 0.6rem 1rem; border-radius: 12px; display: inline-block; max-width: 80%; }
.message.assistant .content { background: #f0f0f0; padding: 0.6rem 1rem; border-radius: 12px; display: inline-block; max-width: 80%; }
.sources { margin-top: 0.3rem; display: flex; gap: 0.5rem; flex-wrap: wrap; }
.source-tag { font-size: 0.75rem; background: #e8e8e8; padding: 0.15rem 0.4rem; border-radius: 4px; }
.input-area { display: flex; padding: 1rem; border-top: 1px solid #eee; gap: 0.5rem; }
.input-area textarea { flex: 1; padding: 0.5rem; border: 1px solid #ddd; border-radius: 6px; resize: none; }
.input-area button { background: #4f46e5; color: white; border: none; padding: 0 1.5rem; border-radius: 6px; cursor: pointer; }
</style>
