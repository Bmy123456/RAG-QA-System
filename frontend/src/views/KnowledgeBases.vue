<template>
  <div class="kb-layout">
    <aside class="sidebar">
      <div class="sidebar-header">
        <h3>知识库</h3>
        <button @click="showCreate = true">+ 新建</button>
      </div>
      <div v-if="showCreate" class="create-form">
        <input v-model="newName" placeholder="知识库名称" />
        <button @click="createKb">创建</button>
        <button @click="showCreate = false">取消</button>
      </div>
      <ul class="kb-list">
        <li v-for="kb in kbs" :key="kb.id" :class="{ active: selectedKb?.id === kb.id }" @click="selectKb(kb)">
          <span>{{ kb.name }}</span>
          <button class="delete-btn" @click.stop="deleteKb(kb.id)">&times;</button>
        </li>
      </ul>
      <div class="sidebar-footer">
        <span>{{ user?.username }}</span>
        <button @click="logout">退出</button>
      </div>
    </aside>
    <main class="main-content">
      <div v-if="!selectedKb" class="placeholder">请选择或创建一个知识库</div>
      <template v-else>
        <div class="toolbar">
          <h2>{{ selectedKb.name }}</h2>
          <router-link :to="`/chat/${selectedKb.id}`" class="chat-btn">开始对话</router-link>
        </div>
        <div class="upload-zone" @drop.prevent="handleDrop" @dragover.prevent>
          <p>拖拽文件到此处上传，或</p>
          <input type="file" ref="fileInput" multiple @change="handleFileSelect" hidden />
          <button @click="$refs.fileInput.click()">选择文件</button>
        </div>
        <div class="doc-list">
          <div v-for="doc in docs" :key="doc.id" class="doc-card">
            <span class="doc-icon">{{ iconForType(doc.file_type) }}</span>
            <div class="doc-info">
              <span class="doc-name">{{ doc.filename }}</span>
              <span class="doc-meta">{{ formatSize(doc.file_size) }} &middot; {{ doc.created_at }}</span>
            </div>
            <span :class="['status', doc.status]">{{ statusLabel(doc.status) }}</span>
            <button @click="deleteDoc(doc.id)" class="delete-btn">&times;</button>
          </div>
        </div>
      </template>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import api from '../api'

const router = useRouter()
const auth = useAuthStore()
const user = ref(auth.user)
const kbs = ref([])
const docs = ref([])
const selectedKb = ref(null)
const showCreate = ref(false)
const newName = ref('')
const fileInput = ref(null)

onMounted(async () => {
  await auth.fetchUser()
  user.value = auth.user
  kbs.value = (await api.get('/kb')).data
})

function iconForType(type) {
  const icons = { pdf: '\u{1F4C4}', docx: '\u{1F4DD}', xlsx: '\u{1F4CA}', pptx: '\u{1F4FD}', image: '\u{1F5BC}', web: '\u{1F310}', email: '\u{1F4E7}', txt: '\u{1F4C3}' }
  return icons[type] || '\u{1F4CE}'
}
function statusLabel(s) { return { processing: '处理中', completed: '已完成', failed: '失败' }[s] || s }
function formatSize(b) { return b < 1024 ? b + 'B' : b < 1048576 ? (b / 1024).toFixed(1) + 'KB' : (b / 1048576).toFixed(1) + 'MB' }

async function selectKb(kb) { selectedKb.value = kb; docs.value = (await api.get(`/documents/${kb.id}`)).data }
async function createKb() { if (newName.value) { await api.post('/kb', { name: newName.value }); showCreate.value = false; newName.value = ''; kbs.value = (await api.get('/kb')).data } }
async function deleteKb(id) { if (confirm('确定删除？')) { await api.delete(`/kb/${id}`); selectedKb.value = null; docs.value = []; kbs.value = (await api.get('/kb')).data } }
async function handleDrop(e) { for (const file of e.dataTransfer.files) await uploadFile(file) }
async function handleFileSelect(e) { for (const file of e.target.files) await uploadFile(file) }
async function uploadFile(file) {
  const form = new FormData(); form.append('file', file)
  await api.post(`/documents/upload/${selectedKb.value.id}`, form)
  docs.value = (await api.get(`/documents/${selectedKb.value.id}`)).data
}
async function deleteDoc(id) { await api.delete(`/documents/${id}`); docs.value = (await api.get(`/documents/${selectedKb.value.id}`)).data }
function logout() { auth.logout(); router.push('/login') }
</script>

<style scoped>
.kb-layout { display: flex; height: 100vh; }
.sidebar { width: 260px; background: #1e1e2e; color: #cdd6f4; display: flex; flex-direction: column; }
.sidebar-header { padding: 1rem; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #313244; }
.sidebar-header button { background: #4f46e5; color: white; border: none; padding: 0.3rem 0.6rem; border-radius: 4px; cursor: pointer; }
.create-form { padding: 0.5rem 1rem; }
.create-form input { width: 100%; padding: 0.3rem; margin-bottom: 0.3rem; }
.create-form button { margin-right: 0.3rem; }
.kb-list { list-style: none; padding: 0; margin: 0; flex: 1; overflow-y: auto; }
.kb-list li { padding: 0.75rem 1rem; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }
.kb-list li:hover, .kb-list li.active { background: #313244; }
.delete-btn { background: none; border: none; color: #f38ba8; cursor: pointer; font-size: 1.2rem; }
.sidebar-footer { padding: 1rem; border-top: 1px solid #313244; display: flex; justify-content: space-between; align-items: center; }
.sidebar-footer button { background: none; border: none; color: #f38ba8; cursor: pointer; }
.main-content { flex: 1; padding: 2rem; overflow-y: auto; }
.placeholder { display: flex; justify-content: center; align-items: center; height: 100%; color: #999; font-size: 1.2rem; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; }
.chat-btn { background: #4f46e5; color: white; padding: 0.5rem 1rem; border-radius: 6px; text-decoration: none; }
.upload-zone { border: 2px dashed #ccc; border-radius: 8px; padding: 2rem; text-align: center; margin-bottom: 1.5rem; }
.upload-zone button { margin-top: 0.5rem; background: #4f46e5; color: white; border: none; padding: 0.4rem 1rem; border-radius: 4px; cursor: pointer; }
.doc-list { display: flex; flex-direction: column; gap: 0.5rem; }
.doc-card { display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem; background: #f8f8f8; border-radius: 6px; }
.doc-icon { font-size: 1.5rem; }
.doc-info { flex: 1; display: flex; flex-direction: column; }
.doc-meta { font-size: 0.8rem; color: #999; }
.status { padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.8rem; }
.status.completed { background: #d4edda; color: #155724; }
.status.processing { background: #fff3cd; color: #856404; }
.status.failed { background: #f8d7da; color: #721c24; }
</style>
