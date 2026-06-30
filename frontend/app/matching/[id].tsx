import { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Pressable, ActivityIndicator, ScrollView } from "react-native";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Button, Avatar, EmptyState } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing, shadow } from "@/src/theme";

type Artisan = { artisan_id: string; name: string; title: string; photo?: string; trade_name: string; rating: number; reviews_count: number; trust_score: number; acceptance_rate: number; response_min: number; distance_km?: number | null; city?: string };
type Mission = { mission_id: string; status: string; urgency_label: string; price_min: number; price_max: number; artisan: Artisan; candidates: string[]; candidate_index: number };

export default function Matching() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [mission, setMission] = useState<Mission | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);

  const load = useCallback(async () => {
    try { setMission(await api<Mission>(`/missions/${id}`)); } catch {}
    setLoading(false);
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const confirm = async () => {
    setActing(true);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    try {
      await api(`/missions/${id}/confirm`, { method: "POST" });
      router.replace({ pathname: "/track/[id]", params: { id: id as string } });
    } catch {} finally { setActing(false); }
  };

  const refuse = async () => {
    setActing(true);
    try {
      const r = await api<{ status: string }>(`/missions/${id}/refuse`, { method: "POST" });
      if (r.status === "no_pro") { await load(); } else { await load(); }
    } catch {} finally { setActing(false); }
  };

  if (loading || !mission) return <View style={styles.center}><ActivityIndicator color={colors.brand} size="large" /></View>;

  if (mission.status === "no_pro") {
    return (
      <View style={[styles.center, { paddingTop: insets.top }]}>
        <EmptyState icon="sad-outline" title="Aucun autre pro disponible" subtitle="Réessayez plus tard ou modifiez votre demande." />
        <Button testID="back-home" title="Retour à l'accueil" onPress={() => router.replace("/(client)")} style={{ marginHorizontal: spacing.xl, alignSelf: "stretch" }} />
      </View>
    );
  }

  const a = mission.artisan;
  const remaining = mission.candidates.length - mission.candidate_index - 1;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="back-button" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Txt weight="bold" size="lg" style={{ flex: 1, textAlign: "center" }}>Votre pro</Txt>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120 }} showsVerticalScrollIndicator={false}>
        <View style={styles.aiBanner}>
          <Ionicons name="sparkles" size={16} color={colors.brand} />
          <Txt weight="semibold" size="sm" color={colors.brand} style={{ marginLeft: 6 }}>Sélectionné par l&apos;IA comme le meilleur match</Txt>
        </View>

        <View style={styles.proCard}>
          <View style={styles.proTop}>
            {a.photo ? <Image source={{ uri: a.photo }} style={styles.proImg} contentFit="cover" /> : <Avatar name={a.name} size={72} />}
            <View style={{ flex: 1, marginLeft: spacing.md }}>
              <Txt weight="extrabold" size="xl">{a.name}</Txt>
              <Txt color={colors.muted} size="sm" numberOfLines={1}>{a.title}</Txt>
              <View style={{ flexDirection: "row", alignItems: "center", marginTop: 4 }}>
                <Ionicons name="star" size={14} color={colors.star} />
                <Txt weight="semibold" size="sm" style={{ marginLeft: 4 }}>{a.rating?.toFixed(1)}</Txt>
                <Txt size="sm" color={colors.muted} style={{ marginLeft: 4 }}>({a.reviews_count})</Txt>
                {a.distance_km != null && <><Ionicons name="location-outline" size={14} color={colors.muted} style={{ marginLeft: spacing.md }} /><Txt size="sm" color={colors.muted}>{a.distance_km} km</Txt></>}
              </View>
            </View>
          </View>

          <View style={styles.trustWrap}>
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm }}>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <Ionicons name="shield-checkmark" size={16} color={colors.brand} />
                <Txt weight="semibold" size="sm" style={{ marginLeft: 6 }}>Trust Score</Txt>
              </View>
              <Txt weight="extrabold" color={colors.brand}>{a.trust_score}/100</Txt>
            </View>
            <View style={styles.gaugeBg}><View style={[styles.gaugeFill, { width: `${a.trust_score}%` }]} /></View>
          </View>

          <View style={styles.metrics}>
            <Metric icon="checkmark-done" label="Acceptation" value={`${a.acceptance_rate}%`} />
            <Metric icon="flash" label="Réponse" value={`~${a.response_min} min`} />
            <Metric icon="construct" label="Métier" value={a.trade_name} />
          </View>
        </View>

        <View style={styles.estimate}>
          <Txt color={colors.muted} size="sm">Estimation pour cette intervention</Txt>
          <Txt weight="extrabold" size="2xl" style={{ marginTop: 2 }}>{mission.price_min}–{mission.price_max} €</Txt>
          <Txt size="sm" color={colors.muted}>Urgence : {mission.urgency_label}</Txt>
        </View>
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <Pressable testID="refuse-button" onPress={refuse} disabled={acting} style={[styles.refuseBtn, { opacity: remaining > 0 ? 1 : 0.4 }]}>
          <Txt weight="bold" color={colors.onSurface}>Un autre pro</Txt>
        </Pressable>
        <Button testID="confirm-button" title="Confirmer" loading={acting} onPress={confirm} style={{ flex: 1.6 }} />
      </View>
    </View>
  );
}

function Metric({ icon, label, value }: { icon: any; label: string; value: string }) {
  return (
    <View style={{ flex: 1, alignItems: "center" }}>
      <Ionicons name={icon} size={16} color={colors.onSurfaceSecondary} />
      <Txt weight="bold" size="sm" style={{ marginTop: 4 }} numberOfLines={1}>{value}</Txt>
      <Txt size="sm" color={colors.muted}>{label}</Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  iconBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  aiBanner: { flexDirection: "row", alignItems: "center", justifyContent: "center", backgroundColor: colors.brand + "1A", borderRadius: radius.pill, paddingVertical: spacing.sm, marginBottom: spacing.lg },
  proCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, ...shadow.card },
  proTop: { flexDirection: "row", alignItems: "center" },
  proImg: { width: 72, height: 72, borderRadius: radius.md },
  trustWrap: { marginTop: spacing.lg },
  gaugeBg: { height: 8, borderRadius: 4, backgroundColor: colors.surfaceTertiary, overflow: "hidden" },
  gaugeFill: { height: 8, borderRadius: 4, backgroundColor: colors.brand },
  metrics: { flexDirection: "row", marginTop: spacing.lg, paddingTop: spacing.lg, borderTopWidth: 1, borderTopColor: colors.border },
  estimate: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, marginTop: spacing.md },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, flexDirection: "row", gap: spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border, paddingHorizontal: spacing.lg, paddingTop: spacing.md },
  refuseBtn: { flex: 1, height: 54, borderRadius: radius.md, borderWidth: 1.5, borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center" },
});
