import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator, Alert, TextInput } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

type MfaStatus = { enabled: boolean; method: string | null };

export default function MfaScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [status, setStatus] = useState<MfaStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [prepared, setPrepared] = useState<any>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setStatus(await api<MfaStatus>("/security/mfa")); } finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const prepare = async () => {
    setBusy(true);
    try {
      const r = await api("/security/mfa/prepare", { method: "POST", body: { method: "totp" } });
      setPrepared(r);
    } catch (e: any) { Alert.alert("Erreur", e.message); }
    finally { setBusy(false); }
  };

  const verify = async () => {
    setBusy(true);
    try {
      await api("/security/mfa/verify", { method: "POST", body: { code } });
      Alert.alert("Succès", "MFA activée avec succès.");
      setPrepared(null); setCode(""); load();
    } catch (e: any) { Alert.alert("Erreur", e.message); }
    finally { setBusy(false); }
  };

  const disable = async () => {
    Alert.alert("Désactiver la MFA ?", "Votre compte sera moins sécurisé.", [
      { text: "Annuler", style: "cancel" },
      { text: "Désactiver", style: "destructive", onPress: async () => {
        try { await api("/security/mfa", { method: "DELETE" }); load(); } catch (e: any) { Alert.alert("Erreur", e.message); }
      }},
    ]);
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"] }}>
      <View style={styles.header}>
        <Pressable testID="back-btn" onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Txt weight="extrabold" size="xl">Double authentification</Txt>
        <View style={{ width: 32 }} />
      </View>

      {loading ? (
        <ActivityIndicator color={colors.brand} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <>
          <View style={styles.card}>
            <View style={styles.iconWrap}>
              <Ionicons name="shield-checkmark" size={40} color={colors.brand} />
            </View>
            <Txt weight="bold" size="lg" style={{ textAlign: "center", marginTop: spacing.md }}>
              {status?.enabled ? "MFA activée" : "Sécurisez votre compte"}
            </Txt>
            <Txt color={colors.muted} size="sm" style={{ textAlign: "center", marginTop: spacing.sm, lineHeight: 20 }}>
              {status?.enabled
                ? `Méthode active : ${status.method?.toUpperCase()}`
                : "L'authentification à 2 facteurs ajoute une couche supplémentaire de sécurité lors de vos connexions."}
            </Txt>
          </View>

          {!status?.enabled && !prepared && (
            <Pressable testID="prepare-mfa" onPress={prepare} disabled={busy} style={[styles.primary, busy && { opacity: 0.5 }]}>
              <Txt weight="bold" color={colors.onBrand}>Activer la MFA (TOTP)</Txt>
            </Pressable>
          )}

          {prepared && (
            <View style={styles.card}>
              <Txt weight="bold" size="base" style={{ marginBottom: spacing.sm }}>Étape 1 — Scannez ce code</Txt>
              <Txt color={colors.muted} size="sm" style={{ marginBottom: spacing.md }}>
                Ajoutez ce compte à votre application d&apos;authentification (Google Authenticator, Authy...).
              </Txt>
              <View style={styles.secretBox}>
                <Txt weight="bold" size="lg" style={{ letterSpacing: 2, textAlign: "center" }}>{prepared.secret}</Txt>
              </View>
              <Txt color={colors.warning} size="sm" style={{ marginTop: spacing.md }}>
                ⚠️ Mode démo : validez avec le code 000000
              </Txt>
              <Txt weight="bold" size="base" style={{ marginTop: spacing.lg, marginBottom: spacing.sm }}>Étape 2 — Vérification</Txt>
              <TextInput
                testID="mfa-code-input"
                value={code}
                onChangeText={setCode}
                placeholder="Code à 6 chiffres"
                placeholderTextColor={colors.muted}
                keyboardType="number-pad"
                maxLength={6}
                style={styles.input}
              />
              <Pressable testID="verify-mfa" onPress={verify} disabled={busy || code.length < 6} style={[styles.primary, (busy || code.length < 6) && { opacity: 0.5 }]}>
                <Txt weight="bold" color={colors.onBrand}>Vérifier & activer</Txt>
              </Pressable>
            </View>
          )}

          {status?.enabled && (
            <Pressable testID="disable-mfa" onPress={disable} style={styles.dangerBtn}>
              <Ionicons name="close-circle-outline" size={20} color={colors.error} />
              <Txt weight="bold" color={colors.error} style={{ marginLeft: spacing.sm }}>Désactiver la MFA</Txt>
            </Pressable>
          )}
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, marginBottom: spacing.lg },
  iconBtn: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
  card: { marginHorizontal: spacing.lg, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg, borderWidth: 1, borderColor: colors.border },
  iconWrap: { width: 72, height: 72, borderRadius: 36, backgroundColor: `${colors.brand}18`, alignItems: "center", justifyContent: "center", alignSelf: "center" },
  primary: { marginHorizontal: spacing.lg, backgroundColor: colors.brand, paddingVertical: spacing.md, borderRadius: radius.md, alignItems: "center", marginTop: spacing.md },
  secretBox: { backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, padding: spacing.lg, borderWidth: 1, borderColor: colors.border },
  input: { backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, padding: spacing.md, color: colors.onSurface, fontSize: 16, borderWidth: 1, borderColor: colors.border, textAlign: "center", letterSpacing: 4 },
  dangerBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", marginTop: spacing.xl, marginHorizontal: spacing.lg, paddingVertical: spacing.md, borderWidth: 1, borderColor: colors.error, borderRadius: radius.md },
});
