import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { getMe, login as apiLogin, register as apiRegister, logout as apiLogout } from '../api/auth'

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  username: string | null
  userRole: string | null
  userId: number | null
  isAuthenticated: boolean

  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string, email?: string) => Promise<void>
  logout: () => void
  fetchUser: () => Promise<void>
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      username: null,
      userRole: null,
      userId: null,
      isAuthenticated: false,

      login: async (username, password) => {
        const res = await apiLogin({ username, password })
        localStorage.setItem('access_token', res.access_token)
        localStorage.setItem('refresh_token', res.refresh_token)
        set({
          accessToken: res.access_token,
          refreshToken: res.refresh_token,
          username,
          isAuthenticated: true,
        })
        await get().fetchUser()
      },

      register: async (username, password, email) => {
        const res = await apiRegister({ username, password, email })
        localStorage.setItem('access_token', res.access_token)
        localStorage.setItem('refresh_token', res.refresh_token)
        set({
          accessToken: res.access_token,
          refreshToken: res.refresh_token,
          username,
          userRole: 'user',
          isAuthenticated: true,
        })
        await get().fetchUser()
      },

      logout: () => {
        apiLogout().catch(() => {})
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        set({
          accessToken: null,
          refreshToken: null,
          username: null,
          userRole: null,
          userId: null,
          isAuthenticated: false,
        })
      },

      fetchUser: async () => {
        try {
          const me = await getMe()
          set({
            username: me.username,
            userRole: me.role,
            userId: me.id,
            isAuthenticated: true,
          })
        } catch {
          get().logout()
        }
      },
    }),
    {
      name: 'rag-auth',
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        username: state.username,
        userRole: state.userRole,
        userId: state.userId,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)
