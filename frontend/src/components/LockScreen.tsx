/**
 * Lock screen — shown when biometric unlock is required at app startup.
 * User can retry Face ID/Touch ID or fallback to full login.
 */
import React, { useEffect, useState } from "react";
import { View, StyleSheet, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withSequence,
  withTiming,
  Easing,
  FadeIn,
} from "react-native-reanimated";
import { Txt } from "@/src/components/ui";
import { useAuth } from "@/src/context/AuthContext";
import { getBiometricSupport, BiometricSupport } from "@/src/utils/biometric";
import { clearToken } from "@/src/api";

const COLORS = {
  bg: "#000000",
  bgSoft: "#1C1C1E",
  white: "#FFFFFF",
  accent: "#FFFFFF",
  secondary: "#D2D2D7",
  muted: "#86868B",
  border: "#2C2C2E",
};

export default function LockScreen({ onFallbackLogin }: { onFallbackLogin: () => void }) {
  const insets = useSafeAreaInsets();
  const { unlockWithBiometric } = useAuth();
  const [sup, setSup] = useState<BiometricSupport | null>(null);
  const [busy, setBusy] = useState(false);

  const glow = useSharedValue(0.5);
  useEffect(() => {
    glow.value = withRepeat(
      withSequence(
        withTiming(1, { duration: 1600, easing: Easing.inOut(Easing.quad) }),
        withTiming(0.5, { duration: 1600, easing: Easing.inOut(Easing.quad) }),
      ),
      -1,
      true,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const glowStyle = useAnimatedStyle(() => ({ opacity: glow.value }));

  useEffect(() => {
    getBiometricSupport().then(setSup);
  }, []);

  const iconName =
    sup?.type === "face"
      ? "scan-outline"
      : sup?.type === "fingerprint"
      ? "finger-print-outline"
      : "lock-closed-outline";

  const label = sup?.label || "Biométrie";

  const tryUnlock = async () => {
    setBusy(true);
    try {
      await unlockWithBiometric();
    } finally {
      setBusy(false);
    }
  };

  const signOutAndLogin = async () => {
    await clearToken();
    onFallbackLogin();
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24 }]}>
      <LinearGradient
        colors={["rgba(255,255,255,0.06)", "transparent"]}
        style={StyleSheet.absoluteFillObject}
        pointerEvents="none"
      />

      <View style={styles.brandRow}>
        <View style={styles.brandDot} />
        <Txt weight="extrabold" size="sm" style={styles.brandText}>FAQTOTUM</Txt>
      </View>

      <Animated.View entering={FadeIn.duration(600)} style={styles.center}>
        <View style={styles.iconOuter}>
          <Animated.View style={[styles.iconGlow, glowStyle]} />
          <View style={styles.iconInner}>
            <Ionicons name={iconName as any} size={48} color={COLORS.accent} />
          </View>
        </View>

        <Txt weight="extrabold" style={styles.title}>Bon retour</Txt>
        <Txt style={styles.subtitle}>
          Déverrouillez avec {label} pour continuer.
        </Txt>
      </Animated.View>

      <View style={styles.actions}>
        <Pressable
          testID="unlock-btn"
          onPress={tryUnlock}
          disabled={busy}
          style={({ pressed }) => [styles.primary, (busy || pressed) && { opacity: 0.85 }]}
        >
          <Ionicons name={iconName as any} size={18} color={COLORS.bg} />
          <Txt weight="bold" style={{ color: COLORS.bg, marginLeft: 8 }}>
            Déverrouiller avec {label}
          </Txt>
        </Pressable>

        <Pressable
          testID="fallback-btn"
          onPress={signOutAndLogin}
          style={({ pressed }) => [styles.tertiary, pressed && { opacity: 0.7 }]}
        >
          <Txt size="sm" style={{ color: COLORS.secondary }}>
            Utiliser un autre compte
          </Txt>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bg,
    paddingHorizontal: 24,
    justifyContent: "space-between",
  },
  brandRow: { flexDirection: "row", alignItems: "center", gap: 8, alignSelf: "center" },
  brandDot: {
    width: 6, height: 6, borderRadius: 3,
    backgroundColor: COLORS.accent,
    shadowColor: COLORS.accent, shadowOpacity: 1, shadowRadius: 6, shadowOffset: { width: 0, height: 0 },
  },
  brandText: { color: COLORS.white, letterSpacing: 4 },
  center: { alignItems: "center", justifyContent: "center", flex: 1, gap: 12 },
  iconOuter: {
    width: 128, height: 128,
    alignItems: "center", justifyContent: "center",
    marginBottom: 20,
  },
  iconGlow: {
    position: "absolute",
    width: 128, height: 128, borderRadius: 64,
    backgroundColor: "rgba(255,255,255,0.10)",
    shadowColor: COLORS.accent, shadowOpacity: 0.6, shadowRadius: 40, shadowOffset: { width: 0, height: 0 },
  },
  iconInner: {
    width: 92, height: 92, borderRadius: 46,
    backgroundColor: COLORS.bgSoft,
    borderWidth: 1, borderColor: "rgba(255,255,255,0.22)",
    alignItems: "center", justifyContent: "center",
  },
  title: { color: COLORS.white, fontSize: 30, letterSpacing: -0.5 },
  subtitle: { color: COLORS.muted, fontSize: 14, textAlign: "center", lineHeight: 20, marginTop: 4 },
  actions: { gap: 12 },
  primary: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: COLORS.accent,
    borderRadius: 22,
    paddingVertical: 18,
    shadowColor: COLORS.accent,
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.35,
    shadowRadius: 20,
    elevation: 6,
  },
  tertiary: {
    alignItems: "center",
    paddingVertical: 12,
  },
});
