import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, Switch, ActivityIndicator } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

type Prefs = { push_enabled: boolean; email_enabled: boolean; sms_enabled: boolean; marketing: boolean; intervention_updates: boolean; new_bookings: boolean };

export default function NotifSettings() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [loading, setLoading] = useState(true);

  useFocusEffect(useCallback(() => {
    (async () => {
      try { setPrefs(await api<Prefs>("/users/me/notifications")); }
      finally { setLoading(false); }
    })();
  }, []));

  const toggle = async (key: keyof Prefs, value: boolean) => {
    if (!prefs) return;
    const next = { ...prefs, [key]: value };
    setPrefs(next);
    await api("/users/me/notifications", { method: "POST", body: { [key]: value } });
  };

  if (loading || !prefs) return <View style={styles.center}><ActivityIndicator color={colors.brand} /></View>;

  const rows: { key: keyof Prefs; icon: any; label: string; sub: string }[] = [
    { key: "push_enabled", icon: "notifications", label: "Notifications push", sub: "Alertes en temps réel sur votre appareil" },
    { key: "email_enabled", icon: "mail", label: "Emails", sub: "Confirmations et reçus" },
    { key: "sms_enabled", icon: "chatbox", label: "SMS", sub: "Alertes critiques (urgences)" },
    { key: "intervention_updates", icon: "construct", label: "Suivi des interventions", sub: "Acceptation, démarrage, fin" },
    { key: "new_bookings", icon: "calendar", label: "Nouvelles réservations", sub: "Confirmations et rappels" },
    { key: "marketing", icon: "gift", label: "Offres et actualités", sub: "Astuces, promotions et nouveautés" },
  ];

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"] }}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Txt weight="extrabold" size="xl">Notifications</Txt>
        <View style={{ width: 32 }} />
      </View>

      <View style={styles.group}>
        {rows.map((r, i) => (
          <View key={r.key} style={[styles.row, i < rows.length - 1 && styles.rowBorder]}>
            <View style={styles.iconWrap}>
              <Ionicons name={r.icon} size={18} color={colors.brand} />
            </View>
            <View style={{ flex: 1, marginLeft: spacing.md }}>
              <Txt weight="semibold">{r.label}</Txt>
              <Txt size="sm" color={colors.muted}>{r.sub}</Txt>
            </View>
            <Switch
              testID={`notif-${r.key}`}
              value={!!prefs[r.key]}
              onValueChange={(v) => toggle(r.key, v)}
              trackColor={{ true: colors.brand, false: colors.surfaceTertiary }}
              thumbColor={colors.onSurface}
            />
          </View>
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, marginBottom: spacing.lg },
  iconBtn: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
  group: { marginHorizontal: spacing.lg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  row: { flexDirection: "row", alignItems: "center", padding: spacing.md, minHeight: 68 },
  rowBorder: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  iconWrap: { width: 36, height: 36, borderRadius: 18, backgroundColor: `${colors.brand}18`, alignItems: "center", justifyContent: "center" },
});
