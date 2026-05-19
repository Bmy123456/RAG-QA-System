<template>
  <div class="history-page">
    <router-link to="/">&larr; 返回知识库</router-link>
    <h2>对话历史</h2>
    <div class="conv-list">
      <div v-for="c in conversations" :key="c.id" class="conv-card" @click="$router.push(`/chat/${kbId}?conv=${c.id}`)">
        <h4>{{ c.title }}</h4>
        <span class="time">{{ c.created_at }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'

const route = useRoute()
const kbId = route.params.kbId
const conversations = ref([])

onMounted(async () => {
  conversations.value = (await api.get(`/chat/conversations/${kbId}`)).data
})
</script>

<style scoped>
.history-page { max-width: 800px; margin: 0 auto; padding: 2rem; }
.conv-list { display: flex; flex-direction: column; gap: 0.5rem; margin-top: 1rem; }
.conv-card { padding: 1rem; background: #f8f8f8; border-radius: 6px; cursor: pointer; }
.conv-card:hover { background: #eee; }
.time { font-size: 0.8rem; color: #999; }
</style>
