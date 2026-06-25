import client from './client'

export interface LoginPayload {
  username: string
  password: string
}

export interface RegisterPayload {
  username: string
  password: string
  email?: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface UserInfo {
  id: number
  username: string
  email: string | null
  role: string
  is_active: boolean
  created_at: string
}

export async function login(data: LoginPayload): Promise<TokenResponse> {
  const res = await client.post('/api/auth/login', data)
  return res.data
}

export async function register(data: RegisterPayload): Promise<TokenResponse> {
  const res = await client.post('/api/auth/register', data)
  return res.data
}

export async function refreshToken(token: string): Promise<TokenResponse> {
  const res = await client.post('/api/auth/refresh', { refresh_token: token })
  return res.data
}

export async function getMe(): Promise<UserInfo> {
  const res = await client.get('/api/auth/me')
  return res.data
}

export async function logout(): Promise<void> {
  await client.post('/api/auth/logout')
}
