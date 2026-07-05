import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { Platform } from "react-native";
import * as WebBrowser from "expo-web-browser";
import * as Linking from "expo-linking";
import { api, setToken, clearToken, getToken } from "@/src/api";

export type User = {
  user_id: string;
  email: string;
  name: string;
  role: "client" | "artisan";
  picture?: string | null;
};

type AuthState = {
  user: User | null;
  loading: boolean;
  register: (email: string, password: string, name: string, role: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  loginWithGoogle: (role: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState>({} as AuthState);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const loadMe = useCallback(async () => {
    try {
      const token = await getToken();
      if (!token) {
        setUser(null);
        return;
      }
      const me = await api<User>("/auth/me");
      setUser(me);
    } catch {
      await clearToken();
      setUser(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      // Web: handle session_id returned in URL from Google auth
      if (Platform.OS === "web" && typeof window !== "undefined") {
        const hash = window.location.hash || "";
        const search = window.location.search || "";
        const match = (hash + search).match(/session_id=([^&]+)/);
        if (match) {
          const pendingRole = (window.localStorage.getItem("pc_pending_role") as string) || "client";
          try {
            const data = await api<{ token: string; user: User }>("/auth/google", {
              method: "POST",
              auth: false,
              body: { session_token: decodeURIComponent(match[1]), role: pendingRole },
            });
            await setToken(data.token);
            setUser(data.user);
          } catch (e) {
            // ignore
          }
          window.history.replaceState(null, "", window.location.pathname);
          setLoading(false);
          return;
        }
      }
      await loadMe();
      setLoading(false);
    })();
  }, [loadMe]);

  const register = async (email: string, password: string, name: string, role: string) => {
    const data = await api<{ token: string; user: User }>("/auth/register", {
      method: "POST",
      auth: false,
      body: { email, password, name, role },
    });
    await setToken(data.token);
    setUser(data.user);
  };

  const login = async (email: string, password: string) => {
    const data = await api<{ token: string; user: User }>("/auth/login", {
      method: "POST",
      auth: false,
      body: { email, password },
    });
    await setToken(data.token);
    setUser(data.user);
  };

  const loginWithGoogle = async (role: string) => {
    if (Platform.OS === "web" && typeof window !== "undefined") {
      window.localStorage.setItem("pc_pending_role", role);
      const redirectUrl = window.location.origin + "/";
      window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
      return;
    }
    const redirectUrl = Linking.createURL("auth");
    const authUrl = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
    const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
    if (result.type !== "success" || !result.url) return;
    const m = result.url.match(/session_id=([^&]+)/);
    if (!m) return;
    const data = await api<{ token: string; user: User }>("/auth/google", {
      method: "POST",
      auth: false,
      body: { session_token: decodeURIComponent(m[1]), role },
    });
    await setToken(data.token);
    setUser(data.user);
  };

  const logout = async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {}
    await clearToken();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, register, login, loginWithGoogle, logout, refresh: loadMe }}>
      {children}
    </AuthContext.Provider>
  );
}
