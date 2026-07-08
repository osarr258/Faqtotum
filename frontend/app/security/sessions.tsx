import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator, Alert } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

type Session = {
  session_id: string;
  device: string;
  browser: string;
  ip: string;
  created_at: string;
  last_seen_at: string;
  is_current: boolean;
};

export default function SessionsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api<{ sessions: Session[] }>("/security/sessions");
      setSessions(r.sessions);
    } catch (e: any) {
      Alert.alert("Erreur", e.message);
    } finally { setLoading(false); }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const revoke = async (sid: string) => {
    Alert.alert("Révoquer cette session ?", "L'appareil sera immédiatement déconnecté.", [
      { text: "Annuler", style: "cancel" },
      {
        text: "Révoquer", style: "destructive", onPress: async () => {
          try {
            await api(`/security/sessions/${sid}`, { method: "DELETE" });
            load();
          } catch (e: any) { Alert.alert("Erreur", e.message); }
        }
      }
    ]);
  };

  const revokeAll = () => {
    Alert.alert(
      "Déconnecter tous les autres appareils ?",
      "Vous resterez connecté sur cet appareil uniquement.",
      [
        { text: "Annuler", style: "cancel" },
        {
          text: "Déconnecter", style: "destructive", onPress: async () => {
            try {
              const r = await api<{ revoked_count: number }>("/security/sessions/revoke-others", { method: "POST" });
              Alert.alert("Succès", `${r.revoked_count} session(s) révoquée(s).`);
              load();
            } catch (e: any) { Alert.alert("Erreur", e.message); }
          }
        }
      ]
    );
  };

  const iconFor = (device: string) => {
    if (device === "iOS" || device === "Android") return "phone-portrait";
    if (device === "macOS" || device === "Windows" || device === "Linux") return "laptop";
    return "desktop";
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"] }}>
      <View style={styles.header}>
        <Pressable testID="back-btn" onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Txt weight="extrabold" size="xl">Sessions actives</Txt>
        <View style={{ width: 32 }} />
      </View>

      {loading ? (
        <ActivityIndicator color={colors.brand} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <>
          <View style={styles.group}>
            {sessions.map((s, i) => (
              <View key={s.session_id} style={[styles.row, i < sessions.length - 1 && styles.rowBorder]}>
                <View style={styles.rowIcon}>
                  <Ionicons name={iconFor(s.device) as any} size={22} color={colors.brand} />
                </View>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: "row", alignItems: "center" }}>
                    <Txt weight="semibold" size="base">{s.device} · {s.browser}</Txt>
                    {s.is_current && (
                      <View style={styles.badge}>
                        <Txt size="sm" weight="semibold" color={colors.success}>Actuel</Txt>
                      </View>
                    )}
                  </View>
                  <Txt color={colors.muted} size="sm">IP : {s.ip}</Txt>
                  <Txt color={colors.muted} size="sm">
                    Vu : {new Date(s.last_seen_at).toLocaleString("fr-FR")}
                  </Txt>
                </View>
                {!s.is_current && (
                  <Pressable testID={`revoke-${s.session_id}`} onPress={() => revoke(s.session_id)} hitSlop={10}>
                    <Ionicons name="trash-outline" size={20} color={colors.error} />
                  </Pressable>
                )}
              </View>
            ))}
          </View>

          {sessions.length > 1 && (
            <Pressable testID="revoke-all-btn" onPress={revokeAll} style={styles.dangerBtn}>
              <Ionicons name="log-out-outline" size={20} color={colors.error} />
              <Txt weight="bold" color={colors.error} style={{ marginLeft: spacing.sm }}>
                Déconnecter tous les autres appareils
              </Txt>
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
  group: { marginHorizontal: spacing.lg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  row: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingVertical: spacing.md, minHeight: 72 },
  rowIcon: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center", marginRight: spacing.md },
  rowBorder: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  badge: { marginLeft: spacing.sm, paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: radius.pill, backgroundColor: `${colors.success}20` },
  dangerBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", marginTop: spacing.xl, marginHorizontal: spacing.lg, paddingVertical: spacing.md, borderWidth: 1, borderColor: colors.error, borderRadius: radius.md },
});
