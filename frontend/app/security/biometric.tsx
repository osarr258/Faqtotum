/**
 * Face ID / Touch ID / Biometric settings screen.
 * Toggle to enable/disable biometric unlock at app startup.
 */
import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, Switch, ActivityIndicator, Alert, Platform } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { useAuth } from "@/src/context/AuthContext";
import { getBiometricSupport, BiometricSupport } from "@/src/utils/biometric";
import { colors, radius, spacing } from "@/src/theme";

export default function BiometricScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { biometricEnabled, enableBiometric, disableBiometric } = useAuth();
  const [sup, setSup] = useState<BiometricSupport | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setSup(await getBiometricSupport());
    setLoading(false);
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const iconName =
    sup?.type === "face"
      ? "scan-outline"
      : sup?.type === "fingerprint"
      ? "finger-print-outline"
      : "lock-closed-outline";

  const label = sup?.label || "Biométrie";

  const toggle = async (v: boolean) => {
    if (Platform.OS === "web") {
      Alert.alert("Non disponible sur le web", "Cette fonctionnalité nécessite l'application mobile.");
      return;
    }
    setBusy(true);
    try {
      if (v) {
        const ok = await enableBiometric();
        if (!ok) {
          Alert.alert("Échec", `Impossible d'activer ${label}.`);
        }
      } else {
        await disableBiometric();
      }
    } finally { setBusy(false); }
  };

  const notAvailable = !sup?.supported;
  const notEnrolled = sup?.supported && !sup?.enrolled;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surface }}
      contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"] }}
    >
      <View style={styles.header}>
        <Pressable testID="back-btn" onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Txt weight="extrabold" size="xl">{label}</Txt>
        <View style={{ width: 32 }} />
      </View>

      {loading ? (
        <ActivityIndicator color={colors.brand} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <>
          <View style={styles.card}>
            <View style={styles.iconWrap}>
              <Ionicons name={iconName as any} size={44} color={colors.brand} />
            </View>
            <Txt weight="bold" size="lg" style={{ textAlign: "center", marginTop: spacing.md }}>
              {biometricEnabled ? `${label} activé` : `Activer ${label}`}
            </Txt>
            <Txt color={colors.muted} size="sm" style={{ textAlign: "center", marginTop: spacing.sm, lineHeight: 20 }}>
              {biometricEnabled
                ? `Vous vous connectez avec ${label}.`
                : `Connectez-vous plus rapidement grâce à ${label}, sans saisir votre mot de passe.`}
            </Txt>
          </View>

          <View style={styles.row}>
            <View style={{ flex: 1 }}>
              <Txt weight="semibold" size="base">Déverrouiller avec {label}</Txt>
              <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>
                {notAvailable
                  ? "Non pris en charge par cet appareil"
                  : notEnrolled
                  ? "Configurez-le dans les réglages système d'abord"
                  : `À l'ouverture de l'app, ${label} sera demandé.`}
              </Txt>
            </View>
            <Switch
              testID="biometric-toggle"
              value={biometricEnabled}
              onValueChange={toggle}
              disabled={busy || notAvailable || !!notEnrolled || Platform.OS === "web"}
              trackColor={{ true: colors.brand, false: colors.surfaceTertiary }}
              thumbColor={colors.onSurface}
            />
          </View>

          <View style={styles.hintBox}>
            <Ionicons name="information-circle-outline" size={16} color={colors.brand} />
            <Txt size="sm" color={colors.muted} style={{ flex: 1, marginLeft: spacing.sm, lineHeight: 18 }}>
              Vos données biométriques restent sur l&apos;appareil. Auxora ne les reçoit jamais.
              Lors d&apos;une déconnexion, {label} est automatiquement désactivé.
            </Txt>
          </View>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, marginBottom: spacing.lg },
  iconBtn: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
  card: {
    marginHorizontal: spacing.lg,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.xl,
    alignItems: "center",
    marginBottom: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  iconWrap: {
    width: 76, height: 76, borderRadius: 38,
    backgroundColor: `${colors.brand}18`,
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: `${colors.brand}44`,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    marginHorizontal: spacing.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    minHeight: 72,
    marginBottom: spacing.md,
  },
  hintBox: {
    flexDirection: "row",
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
});
