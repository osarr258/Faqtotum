import { useEffect, useState, useCallback, useRef } from "react";
import { View, StyleSheet, Pressable, ActivityIndicator, Linking } from "react-native";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Button, Avatar } from "@/src/components/ui";
import TrackMap from "@/src/components/TrackMap";
import { api } from "@/src/api";
import { colors, radius, spacing, shadow } from "@/src/theme";

type Mission = {
  mission_id: string; status: string; eta_remaining?: number; eta_minutes?: number;
  current_lat?: number; current_lng?: number; client_lat: number; client_lng: number;
  artisan_start_lat?: number; artisan_start_lng?: number;
  artisan: { name: string; photo?: string; phone?: string; trade_name: string; rating: number };
};

const STATUS: Record<string, { label: string; icon: any; color: string }> = {
  en_route: { label: "En route vers vous", icon: "car-sport", color: colors.brand },
  arrived: { label: "Arrivé sur place", icon: "checkmark-circle", color: colors.success },
  completed: { label: "Intervention terminée", icon: "flag", color: colors.success },
};

export default function Track() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [m, setM] = useState<Mission | null>(null);
  const [loading, setLoading] = useState(true);
  const [completing, setCompleting] = useState(false);
  const timer = useRef<any>(null);

  const load = useCallback(async () => {
    try { setM(await api<Mission>(`/missions/${id}`)); } catch {}
    setLoading(false);
  }, [id]);

  useEffect(() => {
    load();
    timer.current = setInterval(load, 3000);
    return () => clearInterval(timer.current);
  }, [load]);

  const complete = async () => {
    setCompleting(true);
    try {
      await api(`/missions/${id}/complete`, { method: "POST" });
      clearInterval(timer.current);
      router.replace("/(client)/bookings");
    } catch {} finally { setCompleting(false); }
  };

  if (loading || !m) return <View style={styles.center}><ActivityIndicator color={colors.brand} size="large" /></View>;

  const st = STATUS[m.status] || STATUS.en_route;
  const artisanPt = { lat: m.current_lat ?? m.artisan_start_lat ?? m.client_lat, lng: m.current_lng ?? m.artisan_start_lng ?? m.client_lng };
  const clientPt = { lat: m.client_lat, lng: m.client_lng };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={styles.mapWrap}>
        <TrackMap artisan={artisanPt} client={clientPt} status={m.status} />
        <Pressable testID="back-button" onPress={() => router.replace("/(client)")} style={[styles.backBtn, { top: insets.top + spacing.sm }]}>
          <Ionicons name="close" size={22} color={colors.onSurface} />
        </Pressable>
      </View>

      <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
        <View style={styles.statusRow}>
          <View style={[styles.statusIcon, { backgroundColor: st.color + "22" }]}>
            <Ionicons name={st.icon} size={22} color={st.color} />
          </View>
          <View style={{ flex: 1, marginLeft: spacing.md }}>
            <Txt weight="extrabold" size="lg">{st.label}</Txt>
            {m.status === "en_route" && <Txt color={colors.muted} size="sm">Arrivée estimée dans {m.eta_remaining ?? m.eta_minutes} min</Txt>}
            {m.status === "arrived" && <Txt color={colors.muted} size="sm">Votre artisan est sur place.</Txt>}
          </View>
          {m.status === "en_route" && (
            <View style={styles.etaBubble}>
              <Txt weight="extrabold" size="xl" color={colors.brand}>{m.eta_remaining ?? m.eta_minutes}</Txt>
              <Txt size="sm" color={colors.muted}>min</Txt>
            </View>
          )}
        </View>

        <View style={styles.proRow}>
          {m.artisan.photo ? <Image source={{ uri: m.artisan.photo }} style={styles.proImg} contentFit="cover" /> : <Avatar name={m.artisan.name} size={52} />}
          <View style={{ flex: 1, marginLeft: spacing.md }}>
            <Txt weight="bold" size="base">{m.artisan.name}</Txt>
            <View style={{ flexDirection: "row", alignItems: "center" }}>
              <Ionicons name="star" size={13} color={colors.star} />
              <Txt size="sm" color={colors.muted} style={{ marginLeft: 4 }}>{m.artisan.rating?.toFixed(1)} · {m.artisan.trade_name}</Txt>
            </View>
          </View>
          <Pressable testID="call-button" onPress={() => m.artisan.phone && Linking.openURL(`tel:${m.artisan.phone}`)} style={styles.callBtn}>
            <Ionicons name="call" size={20} color={colors.onBrand} />
          </Pressable>
        </View>

        {(m.status === "arrived" || m.status === "en_route") && (
          <Button testID="complete-button" title="Marquer comme terminé" loading={completing} onPress={complete} style={{ marginTop: spacing.lg }} />
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  mapWrap: { flex: 1, backgroundColor: colors.surfaceSecondary },
  backBtn: { position: "absolute", left: spacing.lg, width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", ...shadow.card },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, borderTopWidth: 1, borderColor: colors.border },
  statusRow: { flexDirection: "row", alignItems: "center" },
  statusIcon: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  etaBubble: { alignItems: "center", paddingHorizontal: spacing.md },
  proRow: { flexDirection: "row", alignItems: "center", marginTop: spacing.lg, paddingTop: spacing.lg, borderTopWidth: 1, borderTopColor: colors.divider },
  proImg: { width: 52, height: 52, borderRadius: radius.md },
  callBtn: { width: 48, height: 48, borderRadius: 24, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
});
