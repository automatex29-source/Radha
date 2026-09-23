import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, setToken, clearToken, getToken, formatApiError } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // null = checking, false = logged out, object = logged in
  const [user, setUser] = useState(null);

  const bootstrap = useCallback(async () => {
    if (!getToken()) {
      setUser(false);
      return;
    }
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch (err) {
      // Only drop the token when the server rejects it; a network blip or
      // backend restart shouldn't log the user out.
      if (err?.response?.status === 401) clearToken();
      setUser(false);
    }
  }, []);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    setToken(data.token);
    setUser(data.user);
  };

  const register = async (name, email, password) => {
    const { data } = await api.post("/auth/register", { name, email, password });
    setToken(data.token);
    setUser(data.user);
  };

  const logout = async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      /* ignore */
    }
    clearToken();
    setUser(false);
  };

  return (
    <AuthContext.Provider value={{ user, login, register, logout, formatApiError }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
