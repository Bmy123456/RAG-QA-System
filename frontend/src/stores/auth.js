import { defineStore } from 'pinia'
import api from '../api'

export const useAuthStore = defineStore('auth', {
  state: () => ({ user: null, token: localStorage.getItem('token') }),
  actions: {
    async login(username, password) {
      const { data } = await api.post('/auth/login', { username, password })
      this.token = data.access_token
      localStorage.setItem('token', data.access_token)
      await this.fetchUser()
    },
    async register(username, email, password) {
      const { data } = await api.post('/auth/register', { username, email, password })
      this.token = data.access_token
      localStorage.setItem('token', data.access_token)
      await this.fetchUser()
    },
    async fetchUser() {
      const { data } = await api.get('/auth/me')
      this.user = data
    },
    logout() {
      this.token = null
      this.user = null
      localStorage.removeItem('token')
    },
  },
})
