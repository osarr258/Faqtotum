import { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, EmptyState } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

type Event = { id: string; type: string; title: string; subtitle: string; date: string; icon: keyof typeof Ionicons.glyphMap };

export default function Timeline() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [grouped, setGrouped] = useState<Record<string, Event[]>>({});
  const [total, setTotal] = useState(0);

  const load = useCallback(async () => {
    try {
      const data = await api<any>(`/properties/${id}/timeline`);
      setGrouped(data.grouped || {});
      setTotal((data.events || []).length);
    } catch {}
  }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const years = Object.keys(grouped).sort().reverse();

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <View style={{ flex: 1, alignItems: "center" }}>
          <Txt weight="bold" size="lg">Timeline</Txt>
          <Txt size="sm" color={colors.muted}>{total} événements</Txt>
        </View>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing["3xl"] * 2 }}>
        {total === 0 ? (
          <EmptyState
            icon="git-branch"
            title="La mémoire de votre bien démarre ici"
            subtitle="Chaque intervention, équipement installé et document ajouté apparaîtra dans cette timeline."
          />
        ) : (
          years.map((y) => (
            <View key={y} style={{ marginBottom: spacing.xl }}>
              <View style={styles.yearHeader}>
                <View style={styles.yearBadge}>
                  <Txt weight="extrabold" size="2xl" color={colors.brand}>{y}</Txt>
                </View>
                <View style={styles.yearLine} />
              </View>

              <View style={{ marginLeft: spacing.md, paddingLeft: spacing.lg, borderLeftWidth: 2, borderLeftColor: colors.border, gap: spacing.md }}>
                {grouped[y].map((ev) => (
                  <View key={`${y}-${ev.id}`} style={styles.event}>
                    <View style={[styles.eventDot, { backgroundColor: colors.brand }]} />
                    <View style={styles.eventCard}>
                      <View style={styles.eventIcon}>
                        <Ionicons name={ev.icon} size={18} color={colors.brand} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Txt weight="bold" numberOfLines={1}>{ev.title}</Txt>
                        <Txt size="sm" color={colors.muted} numberOfLines={1} style={{ marginTop: 2 }}>
                          {ev.subtitle || labelOfType(ev.type)}
                        </Txt>
                        <Txt size="sm" color={colors.muted} style={{ marginTop: 4 }}>{formatDate(ev.date)}</Txt>
                      </View>
                    </View>
                  </View>
                ))}
              </View>
            </View>
          ))
        )}
      </ScrollView>
    </View>
  );
}

function labelOfType(t: string) {
  const m: Record<string, string> = {
    equipment_installed: "Installation d'équipement",
    document: "Document ajouté",
    intervention: "Intervention",
    reminder_done: "Rappel terminé",
  };
  return m[t] || t;
}
function formatDate(iso?: string) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" }); }
  catch { return iso; }
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.surface },
  iconBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  yearHeader: { flexDirection: "row", alignItems: "center", marginBottom: spacing.md },
  yearBadge: {
    paddingHorizontal: spacing.md, paddingVertical: 6,
    borderRadius: radius.md,
    backgroundColor: colors.brand + "18",
    borderWidth: 1, borderColor: colors.brand + "44",
  },
  yearLine: { flex: 1, height: 1, backgroundColor: colors.border, marginLeft: spacing.md },
  event: { flexDirection: "row", alignItems: "center", position: "relative" },
  eventDot: {
    width: 12, height: 12, borderRadius: 6,
    position: "absolute", left: -spacing.lg - 5,
    top: 22,
    borderWidth: 2, borderColor: colors.surface,
  },
  eventCard: {
    flex: 1, flexDirection: "row", alignItems: "center",
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border,
    gap: spacing.md,
  },
  eventIcon: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.brand + "18",
    alignItems: "center", justifyContent: "center",
  },
});
