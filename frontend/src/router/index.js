import { createRouter, createWebHistory } from 'vue-router'
import Login from '../views/Login.vue'
import Register from '../views/Register.vue'
import KnowledgeBases from '../views/KnowledgeBases.vue'
import Chat from '../views/Chat.vue'
import History from '../views/History.vue'

const routes = [
  { path: '/login', component: Login },
  { path: '/register', component: Register },
  { path: '/', component: KnowledgeBases, meta: { requiresAuth: true } },
  { path: '/chat/:kbId', component: Chat, meta: { requiresAuth: true } },
  { path: '/history/:kbId', component: History, meta: { requiresAuth: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) {
    next('/login')
  } else {
    next()
  }
})

export default router
