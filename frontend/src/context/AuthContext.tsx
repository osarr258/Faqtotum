import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { Alert, Platform } from "react-native";
import * as WebBrowser from "expo-web-browser";
import * as Linking from "expo-linking";
import { api, setToken, clearToken, getToken } from "@/src/api";
import {
  authenticateWithBiometric,
  getBiometricSupport,
  isBiometricEnabled,
  markBiometricAsked,
  setBiometricEnabled,
  wasBiometricAsked,
} from "@/src/utils/biometric";

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
  locked: boolean;
  register: (email: string, password: string, name: string, role: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  loginWithGoogle: (role: string) => Promise<void>;
  loginWithApple: (role: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  unlockWithBiometric: () => Promise<boolean>;
  enableBiometric: () => Promise<boolean>;
  disableBiometric: () => Promise<void>;
  biometricEnabled: boolean;
};

const AuthContext = createContext<AuthState>({} as AuthState);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [locked, setLocked] = useState(false);
  const [biometricEnabled, setBiometricEnabledState] = useState(false);

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

  // On app boot: if token exists AND biometric enabled → LOCK until unlock.
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
          } catch {
            // ignore
          }
          window.history.replaceState(null, "", window.location.pathname);
          setLoading(false);
          return;
        }
      }

      const token = await getToken();
      const bioOn = await isBiometricEnabled();
      setBiometricEnabledState(bioOn);

      if (token && bioOn && Platform.OS !== "web") {
        // Require biometric before restoring session
        setLocked(true);
        setLoading(false);
        // Try to unlock immediately
        const ok = await authenticateWithBiometric("Déverrouillez Faqtotum");
        if (ok) {
          setLocked(false);
          await loadMe();
        } else {
          // User cancelled — stay locked, they can retry via UI
        }
        return;
      }

      await loadMe();
      setLoading(false);
    })();
  }, [loadMe]);

  const unlockWithBiometric = useCallback(async () => {
    const ok = await authenticateWithBiometric("Déverrouillez Faqtotum");
    if (ok) {
      setLocked(false);
      await loadMe();
    }
    return ok;
  }, [loadMe]);

  const promptEnableBiometric = useCallback(async () => {
    if (Platform.OS === "web") return;
    const asked = await wasBiometricAsked();
    if (asked) return;
    const alreadyOn = await isBiometricEnabled();
    if (alreadyOn) return;
    const sup = await getBiometricSupport();
    if (!sup.supported || !sup.enrolled) return;

    await markBiometricAsked();
    Alert.alert(
      `Activer ${sup.label} ?`,
      `Connectez-vous plus rapidement grâce à ${sup.label}.`,
      [
        { text: "Plus tard", style: "cancel" },
        {
          text: "Activer",
          onPress: async () => {
            const ok = await authenticateWithBiometric(`Confirmez avec ${sup.label}`);
            if (ok) {
              await setBiometricEnabled(true);
              setBiometricEnabledState(true);
              Alert.alert("Activé", `${sup.label} est maintenant activé.`);
            }
          },
        },
      ]
    );
  }, []);

  const register = async (email: string, password: string, name: string, role: string) => {
    const data = await api<{ token: string; user: User }>("/auth/register", {
      method: "POST",
      auth: false,
      body: { email, password, name, role },
    });
    await setToken(data.token);
    setUser(data.user);
    setLocked(false);
    setTimeout(() => promptEnableBiometric(), 800);
  };

  const login = async (email: string, password: string) => {
    const data = await api<{ token: string; user: User }>("/auth/login", {
      method: "POST",
      auth: false,
      body: { email, password },
    });
    await setToken(data.token);
    setUser(data.user);
    setLocked(false);
    setTimeout(() => promptEnableBiometric(), 800);
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
    setLocked(false);
    setTimeout(() => promptEnableBiometric(), 800);
  };

  const loginWithApple = async (role: string) => {
    if (Platform.OS !== "ios") {
      Alert.alert("Non disponible", "Apple Sign-In n'est disponible que sur iOS.");
      return;
    }
    const AppleAuth = await import("expo-apple-authentication");
    const isAvail = await AppleAuth.isAvailableAsync();
    if (!isAvail) {
      Alert.alert("Non disponible", "Ce compte iCloud ne peut pas utiliser Apple Sign-In.");
      return;
    }
    // Generate a raw nonce; Apple echoes its SHA-256 in the identity token.
    const rawNonce = Array.from({ length: 32 }, () =>
      Math.floor(Math.random() * 36).toString(36),
    ).join("");
    const hashedNonce = await (async () => {
      // Expo Crypto might not be available; fall back to sending raw only.
      try {
        const Crypto = await import("expo-crypto");
        return await Crypto.digestStringAsync(
          Crypto.CryptoDigestAlgorithm.SHA256,
          rawNonce,
        );
      } catch {
        return undefined;
      }
    })();
    const credential = await AppleAuth.signInAsync({
      requestedScopes: [
        AppleAuth.AppleAuthenticationScope.FULL_NAME,
        AppleAuth.AppleAuthenticationScope.EMAIL,
      ],
      nonce: hashedNonce, // Apple hashes it into the JWT `nonce` claim.
    });
    if (!credential?.identityToken) return;
    const data = await api<{ token: string; user: User }>("/auth/apple", {
      method: "POST",
      auth: false,
      body: {
        identity_token: credential.identityToken,
        // First sign-in only: Apple returns fullName + email once.
        email: credential.email || undefined,
        first_name: credential.fullName?.givenName || undefined,
        last_name: credential.fullName?.familyName || undefined,
        nonce: rawNonce, // backend hashes it and compares with the JWT claim.
        role,
      },
    });
    await setToken(data.token);
    setUser(data.user);
    setLocked(false);
    setTimeout(() => promptEnableBiometric(), 800);
  };

  const logout = async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {}
    await clearToken();
    // Also disable biometric on explicit logout so token can't be re-used
    await setBiometricEnabled(false);
    setBiometricEnabledState(false);
    setLocked(false);
    setUser(null);
  };

  const enableBiometric = useCallback(async () => {
    if (Platform.OS === "web") return false;
    const sup = await getBiometricSupport();
    if (!sup.supported) {
      Alert.alert("Non disponible", "Votre appareil ne prend pas en charge la biométrie.");
      return false;
    }
    if (!sup.enrolled) {
      Alert.alert("Non configuré", `Configurez ${sup.label} dans les réglages de votre appareil.`);
      return false;
    }
    const ok = await authenticateWithBiometric(`Confirmez avec ${sup.label}`);
    if (ok) {
      await setBiometricEnabled(true);
      setBiometricEnabledState(true);
    }
    return ok;
  }, []);

  const disableBiometric = useCallback(async () => {
    await setBiometricEnabled(false);
    setBiometricEnabledState(false);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        locked,
        register,
        login,
        loginWithGoogle,
        loginWithApple,
        logout,
        refresh: loadMe,
        unlockWithBiometric,
        enableBiometric,
        disableBiometric,
        biometricEnabled,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
