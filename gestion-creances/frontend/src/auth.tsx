import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api, getToken, setToken, setUnauthorizedHandler } from "./api";

type User = { id: number; username: string; full_name: string; role: string; role_label: string; must_change_password: boolean };
type Ctx = {
  user: User | null; permissions: string[]; loading: boolean;
  login: (u: string, p: string) => Promise<void>; logout: () => Promise<void>; can: (p: string) => boolean; refresh: () => Promise<void>;
};
const AuthCtx = createContext<Ctx>(null as any);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const lastActivity = useRef(Date.now());

  const clear = useCallback(() => {
    setToken(null);
    setUser(null);
    setPermissions([]);
  }, []);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setLoading(false);
      return;
    }
    try {
      const me = await api("/auth/me");
      setUser(me.user);
      setPermissions(me.permissions);
    } catch {
      clear();
    } finally {
      setLoading(false);
    }
  }, [clear]);

  useEffect(() => {
    setUnauthorizedHandler(clear);
    refresh();
  }, [refresh, clear]);

  // Renouvellement du jeton tant que l'utilisateur est actif ; le serveur ferme
  // la session après la durée d'inactivité paramétrée.
  useEffect(() => {
    const mark = () => (lastActivity.current = Date.now());
    window.addEventListener("mousemove", mark);
    window.addEventListener("keydown", mark);
    const t = setInterval(async () => {
      if (!getToken()) return;
      if (Date.now() - lastActivity.current < 10 * 60 * 1000) {
        try {
          const r = await api("/auth/refresh", { method: "POST" });
          setToken(r.access_token);
        } catch { /* géré par le gestionnaire 401 */ }
      }
    }, 10 * 60 * 1000);
    return () => {
      clearInterval(t);
      window.removeEventListener("mousemove", mark);
      window.removeEventListener("keydown", mark);
    };
  }, []);

  const login = async (username: string, password: string) => {
    const r = await api("/auth/login", { body: { username, password } });
    setToken(r.access_token);
    setUser(r.user);
    setPermissions(r.permissions);
  };
  const logout = async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      clear();
    }
  };
  const can = (p: string) => permissions.includes(p);
  return <AuthCtx.Provider value={{ user, permissions, loading, login, logout, can, refresh }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
