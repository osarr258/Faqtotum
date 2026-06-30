import { useState, useCallback } from "react";
import { View, StyleSheet, FlatList, RefreshControl, Pressable } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, EmptyState, StatusBadge } from "@/src/components/ui";
import ReviewModal from "@/src/components/ReviewModal";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

type Booking = { booking_id: string; conversation_id: string; artisan_name: string; trade_name: string; date: string; slot: string; status: string; description: string; reviewed: boolean };

export default function ClientBookings() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [reviewTarget, setReviewTarget] = useState<Booking | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api<Booking[]>("/bookings/mine");
      setBookings(data);
    } catch {}
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Txt weight="extrabold" size="2xl">Mes réservations</Txt>
      </View>
      <FlatList
        data={bookings}
        keyExtractor={(b) => b.booking_id}
        contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: spacing["3xl"], flexGrow: 1 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
        ListEmptyComponent={<EmptyState icon="calendar-outline" title="Aucune réservation" subtitle="Décrivez votre problème, notre IA trouve le meilleur pro." ctaLabel="Décrire mon problème" onCta={() => router.push("/diagnose")} ctaTestID="empty-diagnose-cta" />}
        renderItem={({ item }) => (
          <View testID={`booking-${item.booking_id}`} style={styles.card}>
            <View style={styles.cardTop}>
              <View style={{ flex: 1 }}>
                <Txt weight="bold" size="lg">{item.artisan_name}</Txt>
                <Txt color={colors.muted} size="sm">{item.trade_name}</Txt>
              </View>
              <StatusBadge status={item.status} />
            </View>
            <View style={styles.metaRow}>
              <Ionicons name="calendar-outline" size={16} color={colors.muted} />
              <Txt size="sm" style={{ marginLeft: 6 }}>{item.date}</Txt>
              <Ionicons name="time-outline" size={16} color={colors.muted} style={{ marginLeft: spacing.lg }} />
              <Txt size="sm" style={{ marginLeft: 6 }}>{item.slot}</Txt>
            </View>
            {item.description ? <Txt color={colors.onSurfaceTertiary} size="sm" style={{ marginTop: spacing.sm }}>{item.description}</Txt> : null}
            <View style={styles.actions}>
              <Pressable testID={`message-${item.booking_id}`} onPress={() => router.push({ pathname: "/chat/[id]", params: { id: item.conversation_id, name: item.artisan_name } })} style={[styles.actBtn, { backgroundColor: colors.surfaceSecondary }]}>
                <Ionicons name="chatbubble-ellipses-outline" size={16} color={colors.onSurface} />
                <Txt weight="semibold" size="sm" style={{ marginLeft: 6 }}>Message</Txt>
              </Pressable>
              {item.status === "completed" && (
                item.reviewed ? (
                  <View style={[styles.actBtn, { backgroundColor: "#D1FAE5" }]}>
                    <Ionicons name="checkmark-circle" size={16} color={colors.success} />
                    <Txt weight="semibold" size="sm" color={colors.success} style={{ marginLeft: 6 }}>Avis publié</Txt>
                  </View>
                ) : (
                  <Pressable testID={`review-${item.booking_id}`} onPress={() => setReviewTarget(item)} style={[styles.actBtn, { backgroundColor: colors.brand }]}>
                    <Ionicons name="star" size={16} color={colors.onSurfaceInverse} />
                    <Txt weight="semibold" size="sm" color={colors.onSurfaceInverse} style={{ marginLeft: 6 }}>Noter</Txt>
                  </Pressable>
                )
              )}
            </View>
          </View>
        )}
      />
      <ReviewModal
        visible={!!reviewTarget}
        bookingId={reviewTarget?.booking_id || null}
        targetName={reviewTarget?.artisan_name || ""}
        onClose={() => setReviewTarget(null)}
        onSubmitted={() => { setReviewTarget(null); load(); }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  card: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md },
  cardTop: { flexDirection: "row", alignItems: "center", marginBottom: spacing.md },
  metaRow: { flexDirection: "row", alignItems: "center" },
  actions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  actBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", flex: 1, height: 42, borderRadius: radius.md },
});
