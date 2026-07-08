import { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, RefreshControl } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { Txt, EmptyState } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

type Session = {
  session_id: string;
  status: string;
  detected_trade: string | null;
  urgency: string;
  confidence: number;
  last_message: string;
  final_summary: any;
  created_at: string;
  updated_at: string;
};

const URGENCY_COLORS: Record<string, string> = {
  faible: colors.success, moyenne: colors.warning, elevee: colors.warning, urgence: colors.error,
};
const TRADE_ICONS: Record<string, keyof typeof import("@expo/vector-icons").Ionicons.glyphMap> = {
  plombier: "water", electricien: "flash", chauffagiste: "flame", climaticien: "snow",
  peintre: "color-palette", serrurier: "key", menuisier: "hammer", macon: "cube",
  carreleur: "grid", couvreur: "home", vitrier: "square-outline", jardinier: "leaf",
};

export default function ConciergeHistory() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<Session[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { setItems(await api<Session[]>("/concierge/sessions")); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const startNew = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    router.push({ pathname: "/concierge/[id]", params: { id: "new" } });
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <View style={{ flex: 1, alignItems: "center" }}>
          <Txt weight="bold" size="lg">Mes conversations</Txt>
          <Txt size="sm" color={colors.muted}>{items.length} diagnostic{items.length > 1 ? "s" : ""}</Txt>
        </View>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing["3xl"] * 2 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}>
        <Pressable testID="new-session-btn" onPress={startNew} style={styles.newSessionCard}>
          <LinearGradient colors={[colors.brand + "22", colors.surfaceSecondary]} style={StyleSheet.absoluteFillObject as any} />
          <View style={styles.newIcon}><Ionicons name="sparkles" size={22} color={colors.brand} /></View>
          <View style={{ flex: 1, marginLeft: spacing.md }}>
            <Txt weight="extrabold" size="lg">Nouveau diagnostic</Txt>
            <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>AURA vous guide en quelques questions.</Txt>
          </View>
          <Ionicons name="arrow-forward" size={20} color={colors.brand} />
        </Pressable>

        {items.length === 0 && (
          <EmptyState icon="chatbubbles" title="Aucun diagnostic pour l'instant" subtitle="Démarrez votre première conversation avec AURA." />
        )}

        {items.map((s) => (
          <Pressable
            key={s.session_id}
            testID={`session-${s.session_id}`}
            onPress={() => router.push({ pathname: "/concierge/[id]", params: { id: s.session_id } })}
            style={styles.card}
          >
            <View style={{ flexDirection: "row", alignItems: "center", marginBottom: spacing.sm }}>
              <View style={styles.tradeIcon}>
                <Ionicons name={TRADE_ICONS[s.detected_trade || ""] || "chatbubbles"} size={18} color={colors.brand} />
              </View>
              <View style={{ flex: 1, marginLeft: spacing.md }}>
                <Txt weight="bold" numberOfLines={1}>{s.final_summary?.problem || s.last_message || "Diagnostic en cours"}</Txt>
                <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>{formatRelative(s.updated_at)}</Txt>
              </View>
              {s.status === "completed" ? (
                <View style={styles.statusChip}>
                  <Ionicons name="checkmark-circle" size={14} color={colors.success} />
                  <Txt size="sm" weight="bold" color={colors.success} style={{ marginLeft: 4 }}>Terminé</Txt>
                </View>
              ) : (
                <View style={[styles.statusChip, { backgroundColor: colors.brand + "18", borderColor: colors.brand + "55" }]}>
                  <Txt size="sm" weight="bold" color={colors.brand}>En cours</Txt>
                </View>
              )}
            </View>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
              {s.detected_trade && <Chip icon="hammer" label={s.detected_trade} />}
              {s.urgency && s.urgency !== "faible" && <Chip icon="flame" label={s.urgency} color={URGENCY_COLORS[s.urgency]} />}
              {s.confidence > 0 && <Chip icon="pulse" label={`${s.confidence}% confiance`} />}
            </View>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

function Chip({ icon, label, color }: { icon: keyof typeof import("@expo/vector-icons").Ionicons.glyphMap; label: string; color?: string }) {
  const c = color || colors.muted;
  return (
    <View style={{ flexDirection: "row", alignItems: "center", paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: c + "18", borderWidth: 1, borderColor: c + "44" }}>
      <Ionicons name={icon} size={12} color={c} />
      <Txt size="sm" weight="semibold" color={c} style={{ marginLeft: 4, textTransform: "capitalize" }}>{label}</Txt>
    </View>
  );
}

function formatRelative(iso?: string) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return "à l'instant";
    if (diff < 3600) return `il y a ${Math.floor(diff / 60)} min`;
    if (diff < 86400) return `il y a ${Math.floor(diff / 3600)} h`;
    return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short" });
  } catch { return iso; }
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.surface },
  iconBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  newSessionCard: { flexDirection: "row", alignItems: "center", padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.brand + "55", overflow: "hidden", marginBottom: spacing.lg },
  newIcon: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brand + "22", alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.brand + "55" },
  card: { padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, marginBottom: spacing.md },
  tradeIcon: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.brand + "18", alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.brand + "44" },
  statusChip: { flexDirection: "row", alignItems: "center", paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: colors.success + "18", borderWidth: 1, borderColor: colors.success + "55" },
});
