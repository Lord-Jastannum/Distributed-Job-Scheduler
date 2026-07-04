import { createContext, useContext, useState, useCallback } from 'react'
import { api, setToken } from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [isAuthed, setIsAuthed] = useState(!!localStorage.getItem('token'))

  const login = useCallback(async (email, password) => {
    const data = await api.login(email, password)
    setToken(data.access_token)
    setIsAuthed(true)
  }, [])

  const register = useCallback(async (email, password, name) => {
    await api.register(email, password, name)
    await login(email, password)
  }, [login])

  const logout = useCallback(() => {
    setToken(null)
    setIsAuthed(false)
  }, [])

  return (
    <AuthContext.Provider value={{ isAuthed, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
