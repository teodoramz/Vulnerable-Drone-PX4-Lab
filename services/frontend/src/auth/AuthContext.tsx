import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import api, { setToken as setApiToken } from "../api/client";
import type { User } from "../api/types";

interface AuthState {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>(null!);

export function useAuth(): AuthState {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTok] = useState<string | null>(() => localStorage.getItem("token"));
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setApiToken(token);
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    api
      .get<User>("/api/auth/me")
      .then((r) => setUser(r.data))
      .catch(() => {
        localStorage.removeItem("token");
        setApiToken(null);
        setTok(null);
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, [token]);

  async function login(username: string, password: string): Promise<void> {
    const r = await api.post("/api/auth/login", { username, password });
    const t: string = r.data.access_token;
    localStorage.setItem("token", t);
    setApiToken(t);
    setUser(r.data.user as User);
    setTok(t);
  }

  function logout(): void {
    localStorage.removeItem("token");
    setApiToken(null);
    setTok(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
