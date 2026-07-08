import { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

type Insights = {
  equipment_count: number;
  equipment_ok: number;
  equipment_attention: number;
  document_count: number;
  upcoming_maintenance: number;
  interventions: number;
  money_invested: number;
  average_health: number;
  demo_values: boolean;
};

export default function InsightsScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [ins, setIns] = useState<Insights | null>(null);
  const load = useCallback(async () => {
    try { setIns(await api<Insights>(`/properties/${id}/insights`)); } catch {}
  }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Txt weight="bold" size="lg" style={{ flex: 1, textAlign: "center" }}>Insights</Txt>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing["3xl"] * 2 }}>
        {ins && (
          <>
            <View style={styles.hero}>
              <LinearGradient colors={[colors.brand + "22", colors.surfaceSecondary]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={StyleSheet.absoluteFillObject as any} />
              <Txt color={colors.muted} size="sm" weight="semibold" style={{ letterSpacing: 0.5 }}>SANTÉ MOYENNE</Txt>
              <Txt weight="extrabold" size="4xl" style={{ marginTop: spacing.sm }}>{ins.average_health}%</Txt>
              <View style={styles.healthBar}>
                <View style={[styles.healthFill, { width: `${ins.average_health}%` }]} />
              </View>
              <Txt size="sm" color={colors.muted} style={{ marginTop: spacing.md }}>
                {ins.average_health >= 90 ? "Votre bien est en excellent état." : ins.average_health >= 70 ? "Quelques équipements nécessitent votre attention." : "Plusieurs équipements ont besoin d'un entretien."}
              </Txt>
              {ins.demo_values && (
                <View style={styles.demoBadge}>
                  <Ionicons name="sparkles" size={12} color={colors.brand} />
                  <Txt size="sm" weight="semibold" color={colors.brand} style={{ marginLeft: 4 }}>Valeurs illustratives</Txt>
                </View>
              )}
            </View>

            <View style={styles.grid}>
              <StatCard icon="cog" label="Équipements" value={ins.equipment_count} />
              <StatCard icon="checkmark-circle" label="En bon état" value={ins.equipment_ok} accent={colors.success} />
              <StatCard icon="warning" label="À surveiller" value={ins.equipment_attention} accent={colors.warning} />
              <StatCard icon="document-text" label="Documents" value={ins.document_count} />
              <StatCard icon="notifications" label="À prévoir" value={ins.upcoming_maintenance} accent={ins.upcoming_maintenance > 0 ? colors.warning : undefined} />
              <StatCard icon="briefcase" label="Interventions" value={ins.interventions} />
            </View>

            <View style={styles.moneyCard}>
              <LinearGradient colors={["#2A1F0C", "#0B0B0F"]} style={StyleSheet.absoluteFillObject as any} />
              <View style={styles.moneyIcon}>
                <Ionicons name="cash" size={22} color={colors.brand} />
              </View>
              <Txt color={colors.muted} size="sm" weight="semibold" style={{ letterSpacing: 0.5, marginTop: spacing.md }}>INVESTI DANS CE BIEN</Txt>
              <Txt weight="extrabold" size="3xl" style={{ marginTop: 4 }}>{ins.money_invested.toLocaleString("fr-FR")} €</Txt>
              <Txt size="sm" color={colors.muted} style={{ marginTop: spacing.xs }}>
                Cumul des interventions et équipements enregistrés.
              </Txt>
            </View>

            <View style={styles.futureCard}>
              <Ionicons name="sparkles" size={20} color={colors.brand} />
              <Txt weight="bold" style={{ marginTop: spacing.sm }}>Bientôt : score IA</Txt>
              <Txt size="sm" color={colors.muted} style={{ marginTop: 4, lineHeight: 18 }}>
                {"L'intelligence artificielle analysera l'âge, l'entretien, la marque et l'usage de chaque équipement pour prédire les défaillances."}
              </Txt>
            </View>
          </>
        )}
      </ScrollView>
    </View>
  );
}

function StatCard({ icon, label, value, accent }: { icon: keyof typeof Ionicons.glyphMap; label: string; value: any; accent?: string }) {
  return (
    <View style={styles.statCard}>
      <View style={[styles.statIcon, accent ? { backgroundColor: accent + "22", borderColor: accent + "55" } : undefined]}>
        <Ionicons name={icon} size={18} color={accent || colors.brand} />
      </View>
      <Txt weight="extrabold" size="2xl" style={{ marginTop: spacing.sm }} color={accent || colors.onSurface}>{value}</Txt>
      <Txt size="sm" color={colors.muted}>{label}</Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.surface },
  iconBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  hero: {
    padding: spacing.xl,
    borderRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
    overflow: "hidden",
  },
  healthBar: { height: 10, marginTop: spacing.md, borderRadius: 5, backgroundColor: colors.surfaceTertiary, overflow: "hidden" },
  healthFill: { height: "100%", backgroundColor: colors.brand, borderRadius: 5 },
  demoBadge: {
    alignSelf: "flex-start",
    flexDirection: "row", alignItems: "center",
    marginTop: spacing.md,
    paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.brand + "18",
    borderWidth: 1, borderColor: colors.brand + "55",
  },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginTop: spacing.xl },
  statCard: {
    width: "47%",
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
  },
  statIcon: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.brand + "18",
    borderWidth: 1, borderColor: colors.brand + "44",
    alignItems: "center", justifyContent: "center",
  },
  moneyCard: {
    marginTop: spacing.xl,
    padding: spacing.xl,
    borderRadius: radius.lg,
    borderWidth: 1, borderColor: colors.brand + "44",
    overflow: "hidden",
  },
  moneyIcon: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: colors.brand + "22",
    borderWidth: 1, borderColor: colors.brand + "55",
    alignItems: "center", justifyContent: "center",
  },
  futureCard: {
    marginTop: spacing.xl,
    padding: spacing.lg,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.brand + "22",
    borderStyle: "dashed",
  },
});
