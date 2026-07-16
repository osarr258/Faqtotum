/**
 * Property Budget dashboard
 * Aggregates spend from property_events + linked interventions.
 * Renders 3 blocks: total + monthly bars + by type + top artisans.
 */
import { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, RefreshControl } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing, shadow } from "@/src/theme";

type BudgetResponse = {
  total_cents: number;
  events_count: number;
  by_month: { month: string; cents: number }[];
  by_type: { type: string; cents: number }[];
  top_artisans: { name: string; cents: number }[];
};

const TYPE_LABEL: Record<string, string> = {
  installation: "Installation",
  entretien: "Entretien",
  reparation: "Réparation",
  controle: "Contrôle",
  nettoyage: "Nettoyage",
  sinistre: "Sinistre",
  intervention: "Intervention",
  autre: "Autre",
};

const TYPE_COLOR: Record<string, string> = {
  installation: "#0EA5E9",
  entretien: "#10B981",
  reparation: "#F97316",
  controle: "#8B5CF6",
  nettoyage: "#22D3EE",
  sinistre: "#EF4444",
  intervention: "#F59E0B",
  autre: "#64748B",
};

function euros(cents: number): string {
  return (cents / 100).toLocaleString("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
}

function formatMonth(ym: string): string {
  if (!ym || ym.length < 7) return "—";
  const [y, m] = ym.split("-");
  const d = new Date(Number(y), Number(m) - 1, 1);
  return d.toLocaleDateString("fr-FR", { month: "short", year: "2-digit" });
}

export default function BudgetScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<BudgetResponse | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api<BudgetResponse>(`/properties/${id}/budget`);
      setData(r);
    } catch {}
  }, [id]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const maxMonthly = data?.by_month.reduce((m, r) => Math.max(m, r.cents), 0) || 1;
  const totalByType = data?.by_type.reduce((s, r) => s + r.cents, 0) || 0;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Txt weight="extrabold" size="lg" style={{ flex: 1, textAlign: "center" }}>Budget</Txt>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing["3xl"] * 2 }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
      >
        {/* Total card */}
        <View style={[styles.totalCard, shadow.card]}>
          <Txt size="sm" color={colors.muted} weight="semibold" style={{ letterSpacing: 0.5 }}>DÉPENSES CUMULÉES</Txt>
          <Txt weight="extrabold" style={styles.totalValue}>{euros(data?.total_cents || 0)}</Txt>
          <Txt size="sm" color={colors.muted} style={{ marginTop: 4 }}>
            {data?.events_count || 0} intervention{(data?.events_count || 0) > 1 ? "s" : ""} chiffrée{(data?.events_count || 0) > 1 ? "s" : ""}
          </Txt>
        </View>

        {/* Monthly bars */}
        <SectionTitle>Par mois</SectionTitle>
        {!data || data.by_month.length === 0 ? (
          <EmptyBlock label="Aucune dépense enregistrée sur les 12 derniers mois." />
        ) : (
          <View style={styles.chartCard}>
            <View style={styles.monthlyRow}>
              {data.by_month.map((m) => {
                const h = Math.max(4, (m.cents / maxMonthly) * 130);
                return (
                  <View key={m.month} style={styles.monthlyCol}>
                    <View style={styles.monthlyBarWrap}>
                      <View style={[styles.monthlyBar, { height: h }]} />
                    </View>
                    <Txt size="sm" color={colors.muted} style={{ marginTop: 4, fontSize: 10 }}>{formatMonth(m.month)}</Txt>
                    <Txt size="sm" weight="bold" style={{ fontSize: 10 }}>{Math.round(m.cents / 100)}€</Txt>
                  </View>
                );
              })}
            </View>
          </View>
        )}

        {/* By type */}
        <SectionTitle>Par type</SectionTitle>
        {!data || data.by_type.length === 0 ? (
          <EmptyBlock label="Ajoutez le type d'intervention pour voir la répartition." />
        ) : (
          <View style={styles.card}>
            {data.by_type.map((t) => {
              const pct = totalByType > 0 ? (t.cents / totalByType) * 100 : 0;
              return (
                <View key={t.type} style={styles.typeRow}>
                  <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 4 }}>
                    <View style={{ flexDirection: "row", alignItems: "center" }}>
                      <View style={[styles.typeDot, { backgroundColor: TYPE_COLOR[t.type] || colors.brand }]} />
                      <Txt weight="bold" style={{ marginLeft: 8 }}>{TYPE_LABEL[t.type] || t.type}</Txt>
                    </View>
                    <Txt weight="extrabold">{euros(t.cents)}</Txt>
                  </View>
                  <View style={styles.progressTrack}>
                    <View style={[styles.progressFill, { width: `${pct}%`, backgroundColor: TYPE_COLOR[t.type] || colors.brand }]} />
                  </View>
                </View>
              );
            })}
          </View>
        )}

        {/* Top artisans */}
        <SectionTitle>Top artisans</SectionTitle>
        {!data || data.top_artisans.length === 0 ? (
          <EmptyBlock label="Aucun artisan associé à vos dépenses pour l'instant." />
        ) : (
          <View style={styles.card}>
            {data.top_artisans.map((a, idx) => (
              <View key={a.name} style={styles.artisanRow}>
                <View style={styles.rankPill}>
                  <Txt weight="extrabold" size="sm">{idx + 1}</Txt>
                </View>
                <Txt weight="semibold" style={{ flex: 1, marginLeft: spacing.md }} numberOfLines={1}>{a.name}</Txt>
                <Txt weight="extrabold">{euros(a.cents)}</Txt>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </View>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <Txt color={colors.muted} size="sm" weight="semibold" style={{ marginTop: spacing.xl, marginBottom: spacing.md, letterSpacing: 0.5 }}>
      {String(children).toUpperCase()}
    </Txt>
  );
}

function EmptyBlock({ label }: { label: string }) {
  return (
    <View style={styles.emptyBlock}>
      <Ionicons name="information-circle-outline" size={18} color={colors.muted} />
      <Txt size="sm" color={colors.muted} style={{ marginLeft: 8, flex: 1 }}>{label}</Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: spacing.lg, paddingBottom: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.border,
    backgroundColor: colors.surface,
  },
  iconBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center", justifyContent: "center",
  },
  totalCard: {
    padding: spacing.lg,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
  },
  totalValue: { fontSize: 42, marginTop: 8, letterSpacing: -1 },
  card: {
    padding: spacing.lg,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
  },
  chartCard: {
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
  },
  monthlyRow: {
    flexDirection: "row", alignItems: "flex-end",
    height: 180, gap: 6,
    justifyContent: "space-between",
  },
  monthlyCol: { alignItems: "center", flex: 1 },
  monthlyBarWrap: { height: 130, justifyContent: "flex-end" },
  monthlyBar: {
    width: 12, borderRadius: 6,
    backgroundColor: colors.brand,
  },
  typeRow: { marginBottom: spacing.md },
  typeDot: { width: 10, height: 10, borderRadius: 5 },
  progressTrack: {
    height: 6, borderRadius: 3,
    backgroundColor: colors.border,
    overflow: "hidden",
  },
  progressFill: { height: "100%", borderRadius: 3 },
  artisanRow: {
    flexDirection: "row", alignItems: "center",
    paddingVertical: spacing.sm,
  },
  rankPill: {
    width: 28, height: 28, borderRadius: 14,
    backgroundColor: colors.brand + "1F",
    borderWidth: 1, borderColor: colors.brand + "55",
    alignItems: "center", justifyContent: "center",
  },
  emptyBlock: {
    flexDirection: "row", alignItems: "center",
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
  },
});
