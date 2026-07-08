import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

type Log = { log_id: string; action: string; severity: string; created_at: string; metadata?: any; ip?: string };

const ACTION_LABEL: Record<string, string> = {
  "auth.login": "Connexion réussie",
  "auth.login_failed": "Tentative de connexion échouée",
  "auth.register": "Création de compte",
  "auth.google_login": "Connexion Google",
  "auth.logout": "Déconnexion",
  "password.changed": "Mot de passe modifié",
  "password.change_failed": "Échec changement mot de passe",
  "session.revoke": "Session révoquée",
  "session.revoke_all_others": "Toutes les autres sessions révoquées",
  "mfa.prepared": "MFA préparée",
  "mfa.enabled": "MFA activée",
  "mfa.disabled": "MFA désactivée",
  "gdpr.data_exported": "Export RGPD des données",
  "gdpr.account_deleted": "Suppression du compte RGPD",
  "gdpr.consents_updated": "Consentements RGPD mis à jour",
  "biometrics.registered": "Biométrie enrôlée",
};

export default function AuditScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [logs, setLogs] = useState<Log[]>([]);
  const [loading, setLoading] = useState(true);

  useFocusEffect(useCallback(() => {
    (async () => {
      try {
        const r = await api<{ logs: Log[] }>("/security/audit?limit=100");
        setLogs(r.logs);
      } finally { setLoading(false); }
    })();
  }, []));

  const iconFor = (sev: string) => {
    if (sev === "critical") return "warning";
    if (sev === "warn") return "alert-circle-outline";
    return "checkmark-circle-outline";
  };
  const colorFor = (sev: string) => {
    if (sev === "critical") return colors.error;
    if (sev === "warn") return colors.warning;
    return colors.success;
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"] }}>
      <View style={styles.header}>
        <Pressable testID="back-btn" onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Txt weight="extrabold" size="xl">{"Journal d'activité"}</Txt>
        <View style={{ width: 32 }} />
      </View>

      <Txt color={colors.muted} size="sm" style={{ paddingHorizontal: spacing.lg, marginBottom: spacing.md }}>
        Historique immuable — chaîné cryptographiquement.
      </Txt>

      {loading ? (
        <ActivityIndicator color={colors.brand} style={{ marginTop: spacing["2xl"] }} />
      ) : logs.length === 0 ? (
        <Txt color={colors.muted} style={{ textAlign: "center", marginTop: spacing["2xl"] }}>Aucun événement enregistré.</Txt>
      ) : (
        <View style={styles.group}>
          {logs.map((log, i) => (
            <View key={log.log_id} style={[styles.row, i < logs.length - 1 && styles.rowBorder]}>
              <Ionicons name={iconFor(log.severity) as any} size={20} color={colorFor(log.severity)} style={{ marginRight: spacing.md }} />
              <View style={{ flex: 1 }}>
                <Txt weight="semibold" size="base">{ACTION_LABEL[log.action] || log.action}</Txt>
                <Txt color={colors.muted} size="sm">
                  {new Date(log.created_at).toLocaleString("fr-FR")}{log.ip ? ` · ${log.ip}` : ""}
                </Txt>
              </View>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, marginBottom: spacing.md },
  iconBtn: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
  group: { marginHorizontal: spacing.lg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  row: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingVertical: spacing.md, minHeight: 60 },
  rowBorder: { borderBottomWidth: 1, borderBottomColor: colors.divider },
});
