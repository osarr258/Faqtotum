/**
 * Artisan Subscription — FAQTOTUM v1
 *
 * Écran d'abonnement monochrome, aligné sur le reste de l'espace artisan.
 * Remplace l'ancien design "dark gradient champagne".
 *
 * Structure :
 *   1. Header (Retour + titre)
 *   2. Bannière statut (Actif · À souscrire)
 *   3. Card offre unique : Premium 29€/mois — 5 bénéfices clairs
 *   4. CTA principal + note discrète (paiement simulé pour V1)
 *   5. Modal succès (icône check FAQTOTUM)
 */
import { useCallback, useState } from "react";
import {
  View,
  StyleSheet,
  ScrollView,
  Modal,
  ActivityIndicator,
  Pressable,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Button } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

type Profile = {
  is_subscribed?: boolean;
  subscription_expires_at?: string;
};

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
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const [success, setSuccess] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = await api<Profile>("/artisans/me");
      setProfile(p);
    } catch {
      /* silent */
    }
    setLoading(false);
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const subscribe = async () => {
    if (!profile) {
      router.push("/(artisan)/profile");
      return;
    }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    setPaying(true);
    try {
      await api("/artisans/me/subscribe", { method: "POST" });
      Haptics.notificationAsync(
        Haptics.NotificationFeedbackType.Success,
      ).catch(() => {});
      setSuccess(true);
      await load();
    } catch {
      /* silent */
    } finally {
      setPaying(false);
    }
  };

  const active = profile?.is_subscribed;

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.brand} size="large" />
      </View>
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView
        contentContainerStyle={{
          paddingTop: insets.top + spacing.md,
          paddingBottom: insets.bottom + spacing["3xl"],
        }}
        showsVerticalScrollIndicator={false}
      >
        {/* --- Header ---------------------------------------------- */}
        <View style={styles.header}>
          <Pressable
            testID="back-btn"
            onPress={() => router.back()}
            hitSlop={10}
            style={styles.backBtn}
          >
            <Ionicons name="chevron-back" size={20} color={colors.onSurface} />
          </Pressable>
          <View style={{ flex: 1 }}>
            <Txt size="sm" color={colors.muted}>
              Abonnement
            </Txt>
            <Txt weight="extrabold" size="2xl" style={{ marginTop: 2 }}>
              Faqtotum Premium
            </Txt>
          </View>
        </View>

        {/* --- Status banner -------------------------------------- */}
        {active ? (
          <View style={styles.statusActive}>
            <View style={styles.statusIcon}>
              <Ionicons
                name="checkmark"
                size={16}
                color={colors.textInverse}
              />
            </View>
            <View style={{ flex: 1, marginLeft: spacing.md }}>
              <Txt weight="bold" size="sm">
                Abonnement actif
              </Txt>
              <Txt size="sm" color={colors.muted}>
                Votre profil est référencé auprès des clients.
              </Txt>
            </View>
          </View>
        ) : (
          <View style={styles.statusInactive}>
            <View
              style={[
                styles.statusIcon,
                { backgroundColor: colors.warning },
              ]}
            >
              <Ionicons
                name="alert"
                size={16}
                color={colors.textInverse}
              />
            </View>
            <View style={{ flex: 1, marginLeft: spacing.md }}>
              <Txt weight="bold" size="sm">
                Non référencé
              </Txt>
              <Txt size="sm" color={colors.muted}>
                Souscrivez pour apparaître dans les recherches.
              </Txt>
            </View>
          </View>
        )}

        {/* --- Plan card ------------------------------------------ */}
        <View style={styles.planCard}>
          <View style={styles.planHead}>
            <View style={styles.planTag}>
              <Txt
                weight="extrabold"
                size="sm"
                color={colors.textInverse}
                style={{ letterSpacing: 1.5 }}
              >
                PREMIUM
              </Txt>
            </View>
            <View style={styles.planPrice}>
              <Txt weight="extrabold" size="4xl">
                29
              </Txt>
              <View style={{ marginLeft: 4 }}>
                <Txt weight="bold">€</Txt>
                <Txt size="sm" color={colors.muted}>
                  / mois
                </Txt>
              </View>
            </View>
          </View>

          <View style={styles.planDivider} />

          <View style={{ gap: spacing.md }}>
            {BENEFITS.map((b) => (
              <View key={b} style={styles.benefitRow}>
                <View style={styles.benefitCheck}>
                  <Ionicons
                    name="checkmark"
                    size={12}
                    color={colors.textInverse}
                  />
                </View>
                <Txt style={{ flex: 1, marginLeft: spacing.md }}>{b}</Txt>
              </View>
            ))}
          </View>
        </View>

        {/* --- CTA ----------------------------------------------- */}
        <View style={{ paddingHorizontal: spacing.lg, marginTop: spacing.xl }}>
          <Button
            testID="subscribe-button"
            title={active ? "Renouveler l'abonnement" : "S'abonner maintenant"}
            loading={paying}
            onPress={subscribe}
          />
          <Txt
            size="sm"
            color={colors.muted}
            style={{ textAlign: "center", marginTop: spacing.md }}
          >
            Paiement simulé pour la démo · aucune carte requise
          </Txt>
        </View>

        {/* --- Terms -------------------------------------------- */}
        <View style={styles.termsBlock}>
          <Ionicons name="shield-outline" size={16} color={colors.muted} />
          <Txt
            size="sm"
            color={colors.muted}
            style={{ marginLeft: spacing.sm, flex: 1, lineHeight: 20 }}
          >
            Sans engagement. Résiliation en un clic depuis votre profil.
          </Txt>
        </View>
      </ScrollView>

      {/* --- Success modal ------------------------------------- */}
      <Modal visible={success} transparent animationType="fade">
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <View style={styles.modalIcon}>
              <Ionicons
                name="checkmark"
                size={40}
                color={colors.textInverse}
              />
            </View>
            <Txt
              weight="extrabold"
              size="xl"
              style={{ marginTop: spacing.lg, textAlign: "center" }}
            >
              Bienvenue chez Premium
            </Txt>
            <Txt
              size="sm"
              color={colors.muted}
              style={{ marginTop: 6, textAlign: "center" }}
            >
              Votre profil est désormais référencé et visible par les clients.
            </Txt>
            <Button
              testID="success-close-button"
              title="Continuer"
              onPress={() => setSuccess(false)}
              style={{ marginTop: spacing.xl, alignSelf: "stretch" }}
            />
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.lg,
    gap: spacing.md,
  },
  backBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
    justifyContent: "center",
  },
  statusActive: {
    flexDirection: "row",
    alignItems: "center",
    marginHorizontal: spacing.lg,
    marginBottom: spacing.lg,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  statusInactive: {
    flexDirection: "row",
    alignItems: "center",
    marginHorizontal: spacing.lg,
    marginBottom: spacing.lg,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
  },
  statusIcon: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.brand,
  },
  planCard: {
    marginHorizontal: spacing.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.xl,
    backgroundColor: colors.surface,
  },
  planHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  planTag: {
    backgroundColor: colors.brand,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.sm,
  },
  planPrice: {
    flexDirection: "row",
    alignItems: "flex-end",
  },
  planDivider: {
    height: 1,
    backgroundColor: colors.divider,
    marginVertical: spacing.lg,
  },
  benefitRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  benefitCheck: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.brand,
    alignItems: "center",
    justifyContent: "center",
  },
  termsBlock: {
    flexDirection: "row",
    alignItems: "flex-start",
    marginHorizontal: spacing.lg,
    marginTop: spacing.lg,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
  },
  modalBg: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.5)",
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.xl,
  },
  modalCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.xl,
    alignItems: "center",
    width: "100%",
  },
  modalIcon: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: colors.brand,
    alignItems: "center",
    justifyContent: "center",
  },
});
