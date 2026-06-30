import { useEffect, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator, Modal, TextInput } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Button } from "@/src/components/ui";
import { api } from "@/src/api";
import { useAuth } from "@/src/context/AuthContext";
import { colors, font, fontSize, radius, spacing } from "@/src/theme";

type Artisan = { artisan_id: string; name: string; title: string; bio: string; city: string; hourly_rate: number; rating: number; reviews_count: number; photo?: string; trade_name: string; phone?: string };
type Review = { review_id: string; from_name: string; rating: number; comment: string; created_at: string };

const SLOTS = ["08:00", "10:00", "12:00", "14:00", "16:00", "18:00"];
const DAYS_FR = ["Dim", "Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"];
const MONTHS_FR = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"];

function nextDays(n: number) {
  const out: { iso: string; day: string; num: number; month: string }[] = [];
  const today = new Date();
  for (let i = 0; i < n; i++) {
    const d = new Date(today);
    d.setDate(today.getDate() + i);
    out.push({ iso: d.toISOString().slice(0, 10), day: DAYS_FR[d.getDay()], num: d.getDate(), month: MONTHS_FR[d.getMonth()] });
  }
  return out;
}

export default function ArtisanDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user } = useAuth();

  const [artisan, setArtisan] = useState<Artisan | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);
  const days = nextDays(14);
  const [date, setDate] = useState(days[0].iso);
  const [slot, setSlot] = useState("");
  const [desc, setDesc] = useState("");
  const [showSheet, setShowSheet] = useState(false);
  const [booking, setBooking] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Artisan>(`/artisans/${id}`, { auth: false }).then(setArtisan).catch(() => {}).finally(() => setLoading(false));
    api<Review[]>(`/reviews/artisan/${id}`, { auth: false }).then(setReviews).catch(() => {});
  }, [id]);

  const openSheet = () => {
    if (!slot) { setError("Veuillez choisir un créneau."); return; }
    setError("");
    setShowSheet(true);
  };

  const confirm = async () => {
    setBooking(true);
    setError("");
    try {
      await api("/bookings", { method: "POST", body: { artisan_id: id, date, slot, description: desc } });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      setShowSheet(false);
      setSuccess(true);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBooking(false);
    }
  };

  if (loading || !artisan) {
    return <View style={styles.center}><ActivityIndicator color={colors.brand} size="large" /></View>;
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView contentContainerStyle={{ paddingBottom: 120 }} showsVerticalScrollIndicator={false}>
        <View style={styles.hero}>
          <Image source={{ uri: artisan.photo }} style={StyleSheet.absoluteFill} contentFit="cover" transition={250} />
          <LinearGradient colors={["rgba(0,0,0,0.35)", "transparent", "rgba(24,24,27,0.65)"]} style={StyleSheet.absoluteFill} />
          <Pressable testID="back-button" onPress={() => router.back()} style={[styles.backBtn, { top: insets.top + spacing.sm }]}>
            <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
          </Pressable>
          <View style={styles.heroInfo}>
            <View style={styles.tradePill}><Txt weight="semibold" size="sm" color={colors.onSurfaceInverse}>{artisan.trade_name}</Txt></View>
            <Txt weight="extrabold" size="3xl" color={colors.onSurfaceInverse}>{artisan.name}</Txt>
            <Txt size="base" color="#E4E4E7">{artisan.title}</Txt>
          </View>
        </View>

        <View style={styles.body}>
          <View style={styles.statsRow}>
            <Stat icon="star" label="Note" value={`${artisan.rating.toFixed(1)}`} />
            <View style={styles.statDivider} />
            <Stat icon="chatbubble-ellipses-outline" label="Avis" value={`${artisan.reviews_count}`} />
            <View style={styles.statDivider} />
            <Stat icon="cash-outline" label="Tarif" value={`${artisan.hourly_rate}€/h`} />
          </View>

          <View style={styles.verified}>
            <Ionicons name="shield-checkmark" size={18} color={colors.success} />
            <Txt weight="semibold" size="sm" color={colors.success} style={{ marginLeft: 6 }}>Profil vérifié</Txt>
            <Ionicons name="location-outline" size={16} color={colors.muted} style={{ marginLeft: spacing.lg }} />
            <Txt size="sm" color={colors.muted} style={{ marginLeft: 4 }}>{artisan.city}</Txt>
          </View>

          <Txt weight="bold" size="lg" style={{ marginTop: spacing.xl, marginBottom: spacing.sm }}>À propos</Txt>
          <Txt color={colors.onSurfaceTertiary} style={{ lineHeight: 22 }}>{artisan.bio}</Txt>

          <Txt weight="bold" size="lg" style={{ marginTop: spacing.xl, marginBottom: spacing.md }}>Avis clients ({reviews.length})</Txt>
          {reviews.length === 0 ? (
            <Txt color={colors.muted} size="sm">Aucun avis pour le moment.</Txt>
          ) : (
            reviews.map((r) => (
              <View key={r.review_id} testID={`review-${r.review_id}`} style={styles.reviewCard}>
                <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                  <Txt weight="semibold" size="base">{r.from_name}</Txt>
                  <View style={{ flexDirection: "row", alignItems: "center" }}>
                    {[1, 2, 3, 4, 5].map((n) => (
                      <Ionicons key={n} name={n <= r.rating ? "star" : "star-outline"} size={13} color={colors.star} />
                    ))}
                  </View>
                </View>
                {r.comment ? <Txt color={colors.onSurfaceTertiary} size="sm">{r.comment}</Txt> : null}
              </View>
            ))
          )}

          <Txt weight="bold" size="lg" style={{ marginTop: spacing.xl, marginBottom: spacing.md }}>Choisir une date</Txt>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
            {days.map((d) => {
              const active = d.iso === date;
              return (
                <Pressable key={d.iso} testID={`date-${d.iso}`} onPress={() => { Haptics.selectionAsync().catch(() => {}); setDate(d.iso); }} style={[styles.dayCard, { backgroundColor: active ? colors.brand : colors.surfaceSecondary }]}>
                  <Txt size="sm" color={active ? "#D4D4D8" : colors.muted}>{d.day}</Txt>
                  <Txt weight="bold" size="xl" color={active ? colors.onSurfaceInverse : colors.onSurface}>{d.num}</Txt>
                  <Txt size="sm" color={active ? "#D4D4D8" : colors.muted}>{d.month}</Txt>
                </Pressable>
              );
            })}
          </ScrollView>

          <Txt weight="bold" size="lg" style={{ marginTop: spacing.xl, marginBottom: spacing.md }}>Créneaux disponibles</Txt>
          <View style={styles.slotGrid}>
            {SLOTS.map((s) => {
              const active = s === slot;
              return (
                <Pressable key={s} testID={`slot-${s}`} onPress={() => { Haptics.selectionAsync().catch(() => {}); setSlot(s); }} style={[styles.slot, { backgroundColor: active ? colors.brand : colors.surface, borderColor: active ? colors.brand : colors.border }]}>
                  <Txt weight="semibold" color={active ? colors.onSurfaceInverse : colors.onSurface}>{s}</Txt>
                </Pressable>
              );
            })}
          </View>
          {error && !showSheet ? <Txt color={colors.error} size="sm" style={{ marginTop: spacing.md }}>{error}</Txt> : null}
        </View>
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <Button testID="book-button" title={user?.role === "artisan" ? "Connectez-vous comme client" : "Réserver"} icon="calendar" onPress={openSheet} disabled={user?.role === "artisan"} />
      </View>

      {/* Confirmation sheet */}
      <Modal visible={showSheet} transparent animationType="slide" onRequestClose={() => setShowSheet(false)}>
        <Pressable style={styles.modalBg} onPress={() => setShowSheet(false)} />
        <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
          <View style={styles.handle} />
          <Txt weight="extrabold" size="xl" style={{ marginBottom: spacing.md }}>Confirmer la réservation</Txt>
          <View style={styles.summaryRow}><Txt color={colors.muted}>Artisan</Txt><Txt weight="semibold">{artisan.name}</Txt></View>
          <View style={styles.summaryRow}><Txt color={colors.muted}>Date</Txt><Txt weight="semibold">{date}</Txt></View>
          <View style={styles.summaryRow}><Txt color={colors.muted}>Créneau</Txt><Txt weight="semibold">{slot}</Txt></View>
          <TextInput
            testID="desc-input"
            placeholder="Décrivez votre besoin (optionnel)…"
            placeholderTextColor={colors.muted}
            value={desc}
            onChangeText={setDesc}
            multiline
            style={styles.descInput}
          />
          {error ? <Txt color={colors.error} size="sm" style={{ marginBottom: spacing.sm }}>{error}</Txt> : null}
          <Button testID="confirm-booking-button" title="Confirmer" loading={booking} onPress={confirm} />
        </View>
      </Modal>

      {/* Success */}
      <Modal visible={success} transparent animationType="fade">
        <View style={styles.successBg}>
          <View style={styles.successCard}>
            <View style={styles.successIcon}><Ionicons name="checkmark" size={40} color={colors.onSurfaceInverse} /></View>
            <Txt weight="extrabold" size="xl" style={{ marginTop: spacing.lg, textAlign: "center" }}>Demande envoyée !</Txt>
            <Txt color={colors.muted} style={{ marginTop: spacing.xs, textAlign: "center" }}>{artisan.name} va confirmer votre créneau du {date} à {slot}.</Txt>
            <Button testID="success-ok-button" title="Voir mes réservations" onPress={() => { setSuccess(false); router.replace("/(client)/bookings"); }} style={{ marginTop: spacing.xl, alignSelf: "stretch" }} />
          </View>
        </View>
      </Modal>
    </View>
  );
}

function Stat({ icon, label, value }: { icon: any; label: string; value: string }) {
  return (
    <View style={{ flex: 1, alignItems: "center" }}>
      <Ionicons name={icon} size={18} color={colors.onSurface} />
      <Txt weight="bold" size="base" style={{ marginTop: 4 }}>{value}</Txt>
      <Txt size="sm" color={colors.muted}>{label}</Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  hero: { height: 320, width: "100%" },
  backBtn: { position: "absolute", left: spacing.lg, width: 40, height: 40, borderRadius: 20, backgroundColor: "rgba(255,255,255,0.9)", alignItems: "center", justifyContent: "center" },
  heroInfo: { position: "absolute", left: spacing.lg, right: spacing.lg, bottom: spacing.lg },
  tradePill: { alignSelf: "flex-start", backgroundColor: "rgba(255,255,255,0.25)", paddingHorizontal: spacing.md, paddingVertical: 4, borderRadius: radius.pill, marginBottom: spacing.sm },
  body: { paddingHorizontal: spacing.lg, paddingTop: spacing.lg },
  statsRow: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, paddingVertical: spacing.lg },
  statDivider: { width: 1, height: 36, backgroundColor: colors.border },
  verified: { flexDirection: "row", alignItems: "center", marginTop: spacing.lg },
  reviewCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm },
  dayCard: { width: 64, height: 84, borderRadius: radius.md, alignItems: "center", justifyContent: "center", gap: 2 },
  slotGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  slot: { width: "31%", height: 48, borderRadius: radius.md, borderWidth: 1.5, alignItems: "center", justifyContent: "center" },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border, paddingHorizontal: spacing.lg, paddingTop: spacing.md },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg },
  handle: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: spacing.lg },
  summaryRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  descInput: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, minHeight: 70, fontFamily: font.medium, fontSize: fontSize.base, color: colors.onSurface, marginVertical: spacing.lg, textAlignVertical: "top" },
  successBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", alignItems: "center", justifyContent: "center", padding: spacing.xl },
  successCard: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.xl, alignItems: "center", width: "100%" },
  successIcon: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.success, alignItems: "center", justifyContent: "center" },
});
