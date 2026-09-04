import { createContext, useContext, useEffect, useState } from "react";
import { getCurrentUser, logoutUser } from "../api/auth.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState({ loading: true, authenticated: false, role: null, user: null });
  async function refreshAuth() {
    try { const data = await getCurrentUser(); setAuth({ loading: false, authenticated: data.authenticated, role: data.role || null, user: data.user || null }); }
    catch { setAuth({ loading: false, authenticated: false, role: null, user: null }); }
  }
  useEffect(() => { refreshAuth(); }, []);
  function setAuthenticated(data) { setAuth({ loading: false, authenticated: true, role: data.role, user: data.user }); }
  async function logout() { await logoutUser(); setAuth({ loading: false, authenticated: false, role: null, user: null }); }
  return <AuthContext.Provider value={{ ...auth, refreshAuth, setAuthenticated, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() { return useContext(AuthContext); }
