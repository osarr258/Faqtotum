import { useState, useCallback } from "react";
import { View, StyleSheet, ScrollView, Modal, ActivityIndicator } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Button } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

const BENEFITS = [
  "Profil visible par tous les clients",
  "Réservations illimitées",
  "Badge « Profil vérifié »",
  "Mise en avant dans les recherches",
  "Support prioritaire 7j/7",
];

export default function Subscription() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [profile, setProfile] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const [success, setSuccess] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setProfile(await api<any>("/artisans/me")); } catch {}
    setLoading(false);
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const subscribe = async () => {
    if (!profile) { router.push("/(artisan)/profile"); return; }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    setPaying(true);
    try {
      await api("/artisans/me/subscribe", { method: "POST" });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      setSuccess(true);
      await load();
    } catch {} finally { setPaying(false); }
  };

  const active = profile?.is_subscribed;

  if (loading) return <View style={styles.center}><ActivityIndicator color={colors.brand} size="large" /></View>;

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"] }} showsVerticalScrollIndicator={false}>
      <Txt weight="extrabold" size="2xl" style={{ paddingHorizontal: spacing.lg, marginBottom: spacing.lg }}>Abonnement Pro</Txt>

      {active && (
        <View style={styles.activeBanner}>
          <Ionicons name="checkmark-circle" size={20} color={colors.success} />
          <Txt weight="semibold" size="sm" color={colors.success} style={{ marginLeft: spacing.sm }}>Abonnement actif — vous êtes référencé.</Txt>
        </View>
      )}

      <View style={styles.planWrap}>
        <LinearGradient colors={["#27272A", "#09090B"]} style={styles.plan}>
          <View style={styles.planTag}><Txt weight="bold" size="sm" color={colors.onSurfaceInverse}>POPULAIRE</Txt></View>
          <Txt weight="bold" size="lg" color="#D4D4D8">ProConnect Premium</Txt>
          <View style={{ flexDirection: "row", alignItems: "flex-end", marginTop: spacing.sm }}>
            <Txt weight="extrabold" size="4xl" color={colors.onSurfaceInverse}>29€</Txt>
            <Txt size="base" color="#A1A1AA" style={{ marginBottom: 6, marginLeft: 4 }}>/ mois</Txt>
          </View>
          <View style={{ marginTop: spacing.lg, gap: spacing.md }}>
            {BENEFITS.map((b) => (
              <View key={b} style={{ flexDirection: "row", alignItems: "center" }}>
                <Ionicons name="checkmark-circle" size={20} color={colors.success} />
                <Txt color={colors.onSurfaceInverse} style={{ marginLeft: spacing.sm, flex: 1 }}>{b}</Txt>
              </View>
            ))}
          </View>
        </LinearGradient>
      </View>

      <View style={{ paddingHorizontal: spacing.lg, marginTop: spacing.xl }}>
        <Button
          testID="subscribe-button"
          title={active ? "Renouveler l'abonnement" : "S'abonner maintenant"}
          loading={paying}
          onPress={subscribe}
          icon="card"
        />
        <Txt size="sm" color={colors.muted} style={{ textAlign: "center", marginTop: spacing.md }}>
          Paiement simulé pour la démo — aucune carte requise.
        </Txt>
      </View>

      <Modal visible={success} transparent animationType="fade">
        <View style={styles.successBg}>
          <View style={styles.successCard}>
            <View style={styles.successIcon}><Ionicons name="diamond" size={36} color={colors.onSurfaceInverse} /></View>
            <Txt weight="extrabold" size="xl" style={{ marginTop: spacing.lg, textAlign: "center" }}>Bienvenue chez Premium !</Txt>
            <Txt color={colors.muted} style={{ marginTop: spacing.xs, textAlign: "center" }}>Votre profil est désormais référencé et visible par les clients.</Txt>
            <Button testID="success-close-button" title="Continuer" onPress={() => setSuccess(false)} style={{ marginTop: spacing.xl, alignSelf: "stretch" }} />
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  activeBanner: { flexDirection: "row", alignItems: "center", marginHorizontal: spacing.lg, marginBottom: spacing.lg, backgroundColor: "#D1FAE5", borderRadius: radius.md, padding: spacing.md },
  planWrap: { paddingHorizontal: spacing.lg },
  plan: { borderRadius: radius.lg, padding: spacing.xl },
  planTag: { alignSelf: "flex-start", backgroundColor: colors.success, paddingHorizontal: spacing.md, paddingVertical: 4, borderRadius: radius.pill, marginBottom: spacing.md },
  successBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", alignItems: "center", justifyContent: "center", padding: spacing.xl },
  successCard: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.xl, alignItems: "center", width: "100%" },
  successIcon: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
});
