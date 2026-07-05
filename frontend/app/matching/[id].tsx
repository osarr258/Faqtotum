import { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Pressable, ActivityIndicator, ScrollView } from "react-native";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import Animated, { FadeInDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Button, Avatar, EmptyState, TrustBadges } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing, shadow } from "@/src/theme";

type Artisan = {
  artisan_id: string; name: string; title: string; photo?: string; trade_name: string;
  rating: number; reviews_count: number; trust_score: number; acceptance_rate: number;
  response_min: number; distance_km?: number | null; city?: string; eta_minutes?: number;
  match_label?: string; match_reasons?: string[];
};
type Mission = { mission_id: string; status: string; urgency_label: string; price_min: number; price_max: number; top_matches: Artisan[]; candidates: string[] };

export default function Matching() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [mission, setMission] = useState<Mission | null>(null);
  const [loading, setLoading] = useState(true);
  const [bookingId, setBookingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setMission(await api<Mission>(`/missions/${id}`)); } catch {}
    setLoading(false);
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const book = async (artisanId: string) => {
    setBookingId(artisanId);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    try {
      await api(`/missions/${id}/book`, { method: "POST", body: { artisan_id: artisanId } });
      router.replace({ pathname: "/track/[id]", params: { id: id as string } });
    } catch {} finally { setBookingId(null); }
  };

  if (loading || !mission) return <View style={styles.center}><ActivityIndicator color={colors.brand} size="large" /></View>;

  const matches = mission.top_matches || [];
  if (matches.length === 0) {
    return (
      <View style={[styles.center, { paddingTop: insets.top }]}>
        <EmptyState icon="sad-outline" title="Aucun pro disponible" subtitle="Réessayez plus tard ou modifiez votre demande." ctaLabel="Retour à l'accueil" onCta={() => router.replace("/(client)")} ctaTestID="back-home" />
      </View>
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="back-button" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Txt weight="bold" size="lg" style={{ flex: 1, textAlign: "center" }}>Vos pros</Txt>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing["2xl"] }} showsVerticalScrollIndicator={false}>
        <View style={styles.aiBanner}>
          <Ionicons name="sparkles" size={16} color={colors.brand} />
          <Txt weight="semibold" size="sm" color={colors.brand} style={{ marginLeft: 6 }}>Meilleurs profils sélectionnés par notre IA</Txt>
        </View>
        <Txt color={colors.muted} size="sm" style={{ marginBottom: spacing.lg }}>
          Estimation : {mission.price_min}–{mission.price_max} € · Urgence : {mission.urgency_label}
        </Txt>

        {matches.map((a, i) => (
          <Animated.View key={a.artisan_id} entering={FadeInDown.delay(i * 90).duration(500)} style={[styles.proCard, i === 0 && styles.bestCard]}>
            {i === 0 && (
              <View style={styles.bestTag}>
                <Ionicons name="trophy" size={12} color={colors.onBrand} />
                <Txt weight="bold" size="sm" color={colors.onBrand} style={{ marginLeft: 4 }}>Recommandé par l&apos;IA</Txt>
              </View>
            )}
            {i !== 0 && a.match_label ? (
              <View style={styles.labelTag}>
                <Ionicons name="sparkles" size={11} color={colors.brand} />
                <Txt weight="semibold" size="sm" color={colors.brand} style={{ marginLeft: 4 }}>{a.match_label}</Txt>
              </View>
            ) : null}
            <View style={styles.proTop}>
              {a.photo ? <Image source={{ uri: a.photo }} style={styles.proImg} contentFit="cover" transition={200} /> : <Avatar name={a.name} size={64} />}
              <View style={{ flex: 1, marginLeft: spacing.md }}>
                <Txt weight="extrabold" size="lg" numberOfLines={1}>{a.name}</Txt>
                <Txt color={colors.muted} size="sm" numberOfLines={1}>{a.title}</Txt>
                <View style={{ flexDirection: "row", alignItems: "center", marginTop: 4 }}>
                  <Ionicons name="star" size={13} color={colors.star} />
                  <Txt weight="semibold" size="sm" style={{ marginLeft: 4 }}>{a.rating?.toFixed(1)}</Txt>
                  <Txt size="sm" color={colors.muted} style={{ marginLeft: 4 }}>({a.reviews_count})</Txt>
                  {a.distance_km != null && <Txt size="sm" color={colors.muted} style={{ marginLeft: spacing.md }}>{a.distance_km} km</Txt>}
                </View>
              </View>
            </View>

            <View style={{ marginTop: spacing.md }}>
              <TrustBadges artisan={a} compact />
            </View>

            <View style={styles.metrics}>
              <Metric icon="time" label="Arrivée" value={`~${a.eta_minutes ?? 10} min`} />
              <Metric icon="shield-checkmark" label="Trust" value={`${a.trust_score}/100`} />
              <Metric icon="checkmark-done" label="Accept." value={`${a.acceptance_rate}%`} />
            </View>

            {a.match_reasons && a.match_reasons.length > 0 ? (
              <View style={styles.reasonsBox}>
                <View style={{ flexDirection: "row", alignItems: "center", marginBottom: spacing.sm }}>
                  <Ionicons name="bulb" size={14} color={colors.brand} />
                  <Txt weight="bold" size="sm" color={colors.brand} style={{ marginLeft: 6 }}>Pourquoi l&apos;IA le recommande</Txt>
                </View>
                {a.match_reasons.map((r, ri) => (
                  <View key={ri} style={styles.reasonRow}>
                    <Ionicons name="checkmark-circle" size={14} color={colors.brand} />
                    <Txt size="sm" color={colors.onSurfaceSecondary} style={{ marginLeft: 6, flex: 1 }}>{r}</Txt>
                  </View>
                ))}
              </View>
            ) : null}

            <Button testID={`book-${a.artisan_id}`} title="Réserver ce professionnel" icon="calendar" loading={bookingId === a.artisan_id} onPress={() => book(a.artisan_id)} style={{ marginTop: spacing.lg }} />
          </Animated.View>
        ))}
      </ScrollView>
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
  aiBanner: { flexDirection: "row", alignItems: "center", justifyContent: "center", backgroundColor: colors.brand + "1A", borderRadius: radius.pill, paddingVertical: spacing.sm, marginBottom: spacing.sm },
  proCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, marginBottom: spacing.md, ...shadow.card },
  bestCard: { borderColor: colors.brand + "66" },
  bestTag: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.brand, paddingHorizontal: spacing.sm, paddingVertical: 3, borderRadius: radius.pill, marginBottom: spacing.md },
  labelTag: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.brand + "1A", paddingHorizontal: spacing.sm, paddingVertical: 3, borderRadius: radius.pill, marginBottom: spacing.md },
  reasonsBox: { marginTop: spacing.lg, backgroundColor: colors.brand + "0F", borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.brand + "26" },
  reasonRow: { flexDirection: "row", alignItems: "flex-start", marginBottom: 4 },
  proTop: { flexDirection: "row", alignItems: "center" },
  proImg: { width: 64, height: 64, borderRadius: radius.md },
  metrics: { flexDirection: "row", marginTop: spacing.lg, paddingTop: spacing.lg, borderTopWidth: 1, borderTopColor: colors.border },
});
