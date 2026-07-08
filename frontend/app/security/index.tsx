import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

type Overview = {
  security_score: { score: number; level: string; factors: { label: string; delta: number; ok: boolean }[] };
  active_sessions: number;
  mfa: { enabled: boolean; method: string | null };
  recent_events: { action: string; created_at: string; severity: string }[];
};

export default function SecurityCenter() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api<Overview>("/security/overview");
      setData(r);
    } catch {
      /* handled by UI */
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = () => { setRefreshing(true); load(); };

  const scoreColor = (level?: string) => {
    if (level === "excellent") return colors.success;
    if (level === "bon") return colors.brand;
    if (level === "moyen") return colors.warning;
    return colors.error;
  };

  const rows = [
    { icon: "phone-portrait-outline", label: "Sessions actives", sub: `${data?.active_sessions ?? 0} appareil(s)`, to: "/security/sessions" },
    { icon: "scan-outline", label: "Face ID / Touch ID", sub: "Déverrouillage biométrique", to: "/security/biometric" },
    { icon: "key-outline", label: "Authentification à 2 facteurs", sub: data?.mfa?.enabled ? "Activée" : "Non activée", to: "/security/mfa" },
    { icon: "lock-closed-outline", label: "Changer le mot de passe", sub: "Recommandé tous les 90 jours", to: "/security/password" },
    { icon: "document-text-outline", label: "Journal d'activité", sub: "Historique de vos actions", to: "/security/audit" },
    { icon: "shield-checkmark-outline", label: "Confidentialité & RGPD", sub: "Export, consentements, suppression", to: "/security/privacy" },
  ] as const;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surface }}
      contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"] }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
    >
      <View style={styles.header}>
        <Pressable testID="back-btn" onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Txt weight="extrabold" size="2xl">Sécurité</Txt>
        <View style={{ width: 32 }} />
      </View>

      {loading ? (
        <ActivityIndicator color={colors.brand} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <>
          {/* Security Score */}
          <View style={styles.scoreCard}>
            <View style={styles.scoreRow}>
              <View style={[styles.scoreCircle, { borderColor: scoreColor(data?.security_score.level) }]}>
                <Txt weight="extrabold" size="3xl" color={scoreColor(data?.security_score.level)}>
                  {data?.security_score.score ?? 0}
                </Txt>
                <Txt size="sm" color={colors.muted}>/100</Txt>
              </View>
              <View style={{ flex: 1, marginLeft: spacing.lg }}>
                <Txt weight="bold" size="lg">Score de sécurité</Txt>
                <Txt color={colors.muted} size="sm" style={{ textTransform: "capitalize", marginTop: 2 }}>
                  Niveau : {data?.security_score.level}
                </Txt>
              </View>
            </View>
            <View style={styles.factors}>
              {data?.security_score.factors.map((f, i) => (
                <View key={i} style={styles.factorRow}>
                  <Ionicons
                    name={f.ok ? "checkmark-circle" : "alert-circle"}
                    size={18}
                    color={f.ok ? colors.success : colors.warning}
                  />
                  <Txt size="sm" style={{ marginLeft: spacing.sm, flex: 1 }} color={colors.onSurfaceSecondary}>
                    {f.label}
                  </Txt>
                  {f.delta > 0 && (
                    <Txt size="sm" weight="semibold" color={colors.brand}>+{f.delta}</Txt>
                  )}
                </View>
              ))}
            </View>
          </View>

          {/* Actions */}
          <View style={styles.group}>
            {rows.map((r, i) => (
              <Pressable
                key={r.label}
                testID={`sec-row-${i}`}
                onPress={() => router.push(r.to as any)}
                style={({ pressed }) => [styles.row, { opacity: pressed ? 0.6 : 1 }, i < rows.length - 1 && styles.rowBorder]}
              >
                <View style={styles.rowIcon}>
                  <Ionicons name={r.icon as any} size={20} color={colors.brand} />
                </View>
                <View style={{ flex: 1 }}>
                  <Txt weight="semibold" size="base">{r.label}</Txt>
                  <Txt color={colors.muted} size="sm">{r.sub}</Txt>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.muted} />
              </Pressable>
            ))}
          </View>

          {/* Recent events */}
          {(data?.recent_events?.length ?? 0) > 0 && (
            <View style={{ marginTop: spacing.xl }}>
              <Txt weight="bold" size="lg" style={{ paddingHorizontal: spacing.lg, marginBottom: spacing.md }}>
                Événements récents
              </Txt>
              <View style={styles.group}>
                {data!.recent_events.slice(0, 5).map((e, i) => (
                  <View key={i} style={[styles.row, i < 4 && styles.rowBorder]}>
                    <View style={styles.rowIcon}>
                      <Ionicons
                        name={e.severity === "critical" ? "warning-outline" : "time-outline"}
                        size={18}
                        color={e.severity === "critical" ? colors.warning : colors.muted}
                      />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Txt weight="medium" size="sm">{e.action}</Txt>
                      <Txt color={colors.muted} size="sm">
                        {new Date(e.created_at).toLocaleString("fr-FR")}
                      </Txt>
                    </View>
                  </View>
                ))}
              </View>
            </View>
          )}
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, marginBottom: spacing.lg },
  iconBtn: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
  scoreCard: { marginHorizontal: spacing.lg, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.xl, borderWidth: 1, borderColor: colors.border },
  scoreRow: { flexDirection: "row", alignItems: "center" },
  scoreCircle: { width: 88, height: 88, borderRadius: 44, borderWidth: 3, alignItems: "center", justifyContent: "center" },
  factors: { marginTop: spacing.lg, gap: spacing.sm },
  factorRow: { flexDirection: "row", alignItems: "center" },
  group: { marginHorizontal: spacing.lg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  row: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingVertical: spacing.md, minHeight: 64 },
  rowIcon: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center", marginRight: spacing.md },
  rowBorder: { borderBottomWidth: 1, borderBottomColor: colors.divider },
});
