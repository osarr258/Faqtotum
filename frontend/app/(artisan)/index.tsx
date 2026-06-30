import { useState, useCallback } from "react";
import { View, StyleSheet, FlatList, Pressable, RefreshControl } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, EmptyState, StatusBadge, Avatar } from "@/src/components/ui";
import { useAuth } from "@/src/context/AuthContext";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

type Booking = { booking_id: string; client_name: string; trade_name: string; date: string; slot: string; status: string; description: string };
const FILTERS = [
  { key: "pending", label: "En attente" },
  { key: "accepted", label: "Acceptées" },
  { key: "completed", label: "Terminées" },
];

export default function ArtisanDashboard() {
  const { user } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [hasProfile, setHasProfile] = useState(true);
  const [filter, setFilter] = useState("pending");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [bk, profile] = await Promise.all([api<Booking[]>("/bookings/received"), api<any>("/artisans/me")]);
      setBookings(bk);
      setHasProfile(!!profile);
    } catch {}
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const setStatus = async (id: string, status: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    try {
      await api(`/bookings/${id}`, { method: "PATCH", body: { status } });
      load();
    } catch {}
  };

  const filtered = bookings.filter((b) => b.status === filter);
  const pendingCount = bookings.filter((b) => b.status === "pending").length;
  const acceptedCount = bookings.filter((b) => b.status === "accepted").length;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <View style={{ flexDirection: "row", alignItems: "center" }}>
          <View style={{ flex: 1 }}>
            <Txt color={colors.muted} size="sm">Espace Pro</Txt>
            <Txt weight="extrabold" size="2xl">{user?.name?.split(" ")[0]}</Txt>
          </View>
          <Avatar name={user?.name} size={44} />
        </View>

        <View style={styles.metrics}>
          <View style={styles.metricCard}>
            <Txt weight="extrabold" size="3xl">{pendingCount}</Txt>
            <Txt color={colors.muted} size="sm">Demandes en attente</Txt>
          </View>
          <View style={[styles.metricCard, { backgroundColor: colors.brand }]}>
            <Txt weight="extrabold" size="3xl" color={colors.onSurfaceInverse}>{acceptedCount}</Txt>
            <Txt color="#D4D4D8" size="sm">Missions acceptées</Txt>
          </View>
        </View>
      </View>

      {!hasProfile && (
        <Pressable testID="complete-profile-banner" onPress={() => router.push("/(artisan)/profile")} style={styles.banner}>
          <Ionicons name="alert-circle" size={20} color={colors.warning} />
          <Txt weight="semibold" size="sm" style={{ flex: 1, marginLeft: spacing.sm }}>Complétez votre profil pour être visible.</Txt>
          <Ionicons name="chevron-forward" size={18} color={colors.warning} />
        </Pressable>
      )}

      <View style={styles.segment}>
        {FILTERS.map((f) => {
          const active = filter === f.key;
          return (
            <Pressable key={f.key} testID={`filter-${f.key}`} onPress={() => setFilter(f.key)} style={[styles.segItem, active && styles.segActive]}>
              <Txt weight="semibold" size="sm" color={active ? colors.onSurface : colors.muted}>{f.label}</Txt>
            </Pressable>
          );
        })}
      </View>

      <FlatList
        data={filtered}
        keyExtractor={(b) => b.booking_id}
        contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: spacing["3xl"], flexGrow: 1 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
        ListEmptyComponent={<EmptyState icon="calendar-outline" title="Aucune mission ici" subtitle="Les nouvelles demandes apparaîtront dans cet onglet." />}
        renderItem={({ item }) => (
          <View testID={`job-${item.booking_id}`} style={styles.card}>
            <View style={styles.cardTop}>
              <View style={{ flex: 1 }}>
                <Txt weight="bold" size="lg">{item.client_name}</Txt>
                <View style={{ flexDirection: "row", alignItems: "center", marginTop: 2 }}>
                  <Ionicons name="calendar-outline" size={14} color={colors.muted} />
                  <Txt size="sm" color={colors.muted} style={{ marginLeft: 4 }}>{item.date} · {item.slot}</Txt>
                </View>
              </View>
              <StatusBadge status={item.status} />
            </View>
            {item.description ? <Txt color={colors.onSurfaceTertiary} size="sm" style={{ marginTop: spacing.sm }}>{item.description}</Txt> : null}
            {item.status === "pending" && (
              <View style={styles.actions}>
                <Pressable testID={`decline-${item.booking_id}`} onPress={() => setStatus(item.booking_id, "declined")} style={[styles.actionBtn, { backgroundColor: colors.surfaceSecondary }]}>
                  <Txt weight="bold" color={colors.error}>Refuser</Txt>
                </Pressable>
                <Pressable testID={`accept-${item.booking_id}`} onPress={() => setStatus(item.booking_id, "accepted")} style={[styles.actionBtn, { backgroundColor: colors.brand }]}>
                  <Txt weight="bold" color={colors.onSurfaceInverse}>Accepter</Txt>
                </Pressable>
              </View>
            )}
            {item.status === "accepted" && (
              <Pressable testID={`complete-${item.booking_id}`} onPress={() => setStatus(item.booking_id, "completed")} style={[styles.actionBtn, { backgroundColor: colors.success, marginTop: spacing.md }]}>
                <Txt weight="bold" color={colors.onSuccess}>Marquer comme terminée</Txt>
              </Pressable>
            )}
          </View>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  metrics: { flexDirection: "row", gap: spacing.md, marginTop: spacing.lg },
  metricCard: { flex: 1, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg },
  banner: { flexDirection: "row", alignItems: "center", marginHorizontal: spacing.lg, marginBottom: spacing.sm, backgroundColor: "#FEF3C7", borderRadius: radius.md, padding: spacing.md },
  segment: { flexDirection: "row", marginHorizontal: spacing.lg, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: 4, marginBottom: spacing.md },
  segItem: { flex: 1, height: 38, alignItems: "center", justifyContent: "center", borderRadius: radius.sm },
  segActive: { backgroundColor: colors.surface },
  card: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md },
  cardTop: { flexDirection: "row", alignItems: "center" },
  actions: { flexDirection: "row", gap: spacing.md, marginTop: spacing.md },
  actionBtn: { flex: 1, height: 46, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
});
