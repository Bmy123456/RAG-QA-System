<template>
  <div class="auth-container">
    <form @submit.prevent="handleRegister" class="auth-form">
      <h2>注册</h2>
      <input v-model="username" placeholder="用户名" required />
      <input v-model="email" type="email" placeholder="邮箱" required />
      <input v-model="password" type="password" placeholder="密码" required />
      <button type="submit" :disabled="loading">注册</button>
      <p v-if="error" class="error">{{ error }}</p>
      <p>已有账号？<router-link to="/login">登录</router-link></p>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const username = ref('')
const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function handleRegister() {
  loading.value = true
  error.value = ''
  try {
    await auth.register(username.value, email.value, password.value)
    router.push('/')
  } catch (e) {
    error.value = e.response?.data?.detail || '注册失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-container { display: flex; justify-content: center; align-items: center; min-height: 100vh; background: #f5f5f5; }
.auth-form { background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); width: 360px; }
.auth-form h2 { margin-bottom: 1.5rem; text-align: center; }
.auth-form input { width: 100%; padding: 0.6rem; margin-bottom: 1rem; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
.auth-form button { width: 100%; padding: 0.6rem; background: #4f46e5; color: white; border: none; border-radius: 4px; cursor: pointer; }
.auth-form button:disabled { opacity: 0.6; }
.error { color: #e53e3e; margin-top: 0.5rem; }
</style>
