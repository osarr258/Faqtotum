/**
 * Artisan Stripe Connect — onboarding, status, payouts.
 * The artisan connects a Stripe Express account so payments received
 * from clients can be transferred to their bank account (after platform commission).
 */
import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator, Alert, Platform } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, { FadeIn, FadeInUp } from "react-native-reanimated";
import * as Haptics from "expo-haptics";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";

const COLORS = {
  bg: "#0B0B0B", bgSoft: "#141416", white: "#FFFFFF", accent: "#C8A96B",
  secondary: "#B8B8B8", muted: "#6E6E73", border: "#1F1F22", success: "#34D399", error: "#F87171",
};

type ConnectStatus = {
  connected: boolean;
  stripe_account_id?: string;
  charges_enabled?: boolean;
  payouts_enabled?: boolean;
  details_submitted?: boolean;
  requirements?: { currently_due?: string[] };
  mock_mode?: boolean;
};

export default function ConnectScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [status, setStatus] = useState<ConnectStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const s = await api<ConnectStatus>("/connect/status");
      setStatus(s);
    } catch (e: any) {
      Alert.alert("Erreur", e?.message);
    } finally { setLoading(false); }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const startOnboarding = async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    setBusy(true);
    try {
      const r = await api<{ onboarding_url: string; mock_mode?: boolean }>("/connect/onboard", {
        method: "POST",
        body: { country: "FR" },
      });
      const url = r.onboarding_url;
      if (Platform.OS === "web") {
        // Same-origin mock in web preview
        window.location.href = url;
      } else {
        const res = await WebBrowser.openBrowserAsync(url);
        // When user returns, refresh status
        if (res.type === "cancel" || res.type === "dismiss") {
          setTimeout(load, 500);
        }
      }
    } catch (e: any) {
      Alert.alert("Erreur", e?.message);
    } finally { setBusy(false); }
  };

  const openDashboard = async () => {
    Haptics.selectionAsync().catch(() => {});
    Alert.alert("Dashboard Stripe", "Le dashboard Stripe Express sera accessible ici une fois vos vraies clés Stripe configurées.");
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={COLORS.accent} size="large" />
      </View>
    );
  }

  const chargesOk = !!status?.charges_enabled;
  const payoutsOk = !!status?.payouts_enabled;
  const fullyReady = chargesOk && payoutsOk && !!status?.details_submitted;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={{ paddingTop: insets.top + 12, paddingBottom: insets.bottom + 40 }}
    >
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={COLORS.white} />
        </Pressable>
        <Txt weight="extrabold" size="xl" style={{ color: COLORS.white }}>Paiements</Txt>
        <View style={{ width: 40 }} />
      </View>

      <Animated.View entering={FadeIn.duration(400)} style={styles.heroCard}>
        <View style={styles.stripeIcon}>
          <Ionicons name="card" size={30} color={COLORS.accent} />
        </View>
        <Txt weight="extrabold" style={styles.heroTitle}>Stripe Connect</Txt>
        <Txt style={styles.heroSub}>
          Recevez vos paiements sur votre compte bancaire, en toute sécurité.
        </Txt>
      </Animated.View>

      {/* Status */}
      <Animated.View entering={FadeInUp.delay(150).duration(400)} style={styles.statusCard}>
        <View style={styles.statusRow}>
          <View style={[styles.statusDot, { backgroundColor: fullyReady ? COLORS.success : COLORS.accent }]} />
          <Txt weight="bold" size="lg" style={{ color: COLORS.white, marginLeft: 10 }}>
            {fullyReady ? "Compte actif" : status?.connected ? "Configuration en cours" : "Non connecté"}
          </Txt>
        </View>
        <Txt size="sm" style={{ color: COLORS.muted, marginTop: 6, lineHeight: 20 }}>
          {fullyReady
            ? "Vous recevez automatiquement vos paiements après chaque intervention validée."
            : status?.connected
            ? "Terminez votre configuration Stripe pour activer les paiements."
            : "Connectez votre compte Stripe pour recevoir vos paiements."}
        </Txt>

        {status?.connected && (
          <View style={styles.checks}>
            <CheckRow ok={!!status.details_submitted} label="Informations transmises" />
            <CheckRow ok={chargesOk} label="Encaissements activés" />
            <CheckRow ok={payoutsOk} label="Virements bancaires activés" />
          </View>
        )}

        {status?.mock_mode && (
          <View style={styles.mockBanner}>
            <Ionicons name="information-circle-outline" size={14} color={COLORS.accent} />
            <Txt size="sm" style={{ color: COLORS.muted, marginLeft: 6, flex: 1, lineHeight: 18 }}>
              Mode démo — vraie intégration Stripe active dès que les clés Stripe réelles sont fournies.
            </Txt>
          </View>
        )}
      </Animated.View>

      {/* Actions */}
      <View style={{ paddingHorizontal: 20, marginTop: 20, gap: 10 }}>
        {!status?.connected || !fullyReady ? (
          <Pressable
            testID="start-onboarding"
            onPress={startOnboarding}
            disabled={busy}
            style={({ pressed }) => [styles.primary, (busy || pressed) && { opacity: 0.85 }]}
          >
            {busy ? <ActivityIndicator color={COLORS.bg} /> : (
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <Ionicons name="link" size={18} color={COLORS.bg} />
                <Txt weight="bold" style={{ color: COLORS.bg, marginLeft: 8 }}>
                  {status?.connected ? "Terminer la configuration" : "Connecter mon compte Stripe"}
                </Txt>
              </View>
            )}
          </Pressable>
        ) : (
          <Pressable
            testID="open-dashboard"
            onPress={openDashboard}
            style={({ pressed }) => [styles.secondary, pressed && { opacity: 0.7 }]}
          >
            <Ionicons name="open-outline" size={18} color={COLORS.white} />
            <Txt weight="semibold" style={{ color: COLORS.white, marginLeft: 8 }}>
              Voir mes paiements sur Stripe
            </Txt>
          </Pressable>
        )}
      </View>

      {/* Info boxes */}
      <Animated.View entering={FadeInUp.delay(250).duration(400)} style={styles.info}>
        <Txt weight="bold" size="base" style={{ color: COLORS.white, marginBottom: 10 }}>Comment ça marche ?</Txt>
        <InfoStep n="1" title="Le client paie" sub="Acompte + solde via Apple Pay ou carte" />
        <InfoStep n="2" title="Faqtotum garde en séquestre" sub="Fonds sécurisés jusqu'à validation de la mission" />
        <InfoStep n="3" title="Vous recevez le paiement" sub="Après validation, transfert automatique sur votre banque (commission Faqtotum déduite)" />
      </Animated.View>

      <Animated.View entering={FadeInUp.delay(350).duration(400)} style={styles.legal}>
        <Ionicons name="shield-checkmark" size={14} color={COLORS.muted} />
        <Txt size="sm" style={{ color: COLORS.muted, marginLeft: 6, flex: 1, lineHeight: 18 }}>
          Faqtotum utilise Stripe pour traiter les paiements en toute conformité (PCI-DSS, PSD2, KYC). Vos données bancaires ne sont jamais stockées par Faqtotum.
        </Txt>
      </Animated.View>
    </ScrollView>
  );
}

function CheckRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", marginTop: 8 }}>
      <Ionicons name={ok ? "checkmark-circle" : "ellipse-outline"} size={16} color={ok ? COLORS.success : COLORS.muted} />
      <Txt size="sm" style={{ color: ok ? COLORS.white : COLORS.secondary, marginLeft: 8 }}>{label}</Txt>
    </View>
  );
}

function InfoStep({ n, title, sub }: { n: string; title: string; sub: string }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "flex-start", marginTop: 10 }}>
      <View style={styles.stepBubble}>
        <Txt weight="extrabold" size="sm" style={{ color: COLORS.accent }}>{n}</Txt>
      </View>
      <View style={{ flex: 1, marginLeft: 12 }}>
        <Txt weight="bold" size="sm" style={{ color: COLORS.white }}>{title}</Txt>
        <Txt size="sm" style={{ color: COLORS.muted, marginTop: 2, lineHeight: 18 }}>{sub}</Txt>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, backgroundColor: COLORS.bg, alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    marginBottom: 16,
  },
  iconBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: COLORS.bgSoft,
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: COLORS.border,
  },
  heroCard: {
    marginHorizontal: 20,
    padding: 24,
    borderRadius: 20,
    backgroundColor: COLORS.bgSoft,
    borderWidth: 1, borderColor: COLORS.border,
    alignItems: "center",
  },
  stripeIcon: {
    width: 64, height: 64, borderRadius: 32,
    backgroundColor: "rgba(200,169,107,0.15)",
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: "rgba(200,169,107,0.3)",
    marginBottom: 12,
  },
  heroTitle: { color: COLORS.white, fontSize: 22 },
  heroSub: { color: COLORS.secondary, fontSize: 13, textAlign: "center", marginTop: 8, lineHeight: 20, paddingHorizontal: 10 },
  statusCard: {
    marginHorizontal: 20, marginTop: 16,
    padding: 18,
    backgroundColor: COLORS.bgSoft,
    borderRadius: 20,
    borderWidth: 1, borderColor: COLORS.border,
  },
  statusRow: { flexDirection: "row", alignItems: "center" },
  statusDot: {
    width: 10, height: 10, borderRadius: 5,
    shadowColor: COLORS.accent, shadowOpacity: 0.8, shadowRadius: 6, shadowOffset: { width: 0, height: 0 },
  },
  checks: { marginTop: 14, gap: 2 },
  mockBanner: {
    flexDirection: "row",
    alignItems: "flex-start",
    marginTop: 14,
    padding: 10,
    backgroundColor: "rgba(200,169,107,0.06)",
    borderRadius: 12,
    borderWidth: 1, borderColor: "rgba(200,169,107,0.15)",
  },
  primary: {
    backgroundColor: COLORS.accent,
    borderRadius: 16,
    paddingVertical: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  secondary: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 16,
    paddingVertical: 16,
    borderWidth: 1, borderColor: COLORS.border,
    backgroundColor: COLORS.bgSoft,
  },
  info: {
    marginHorizontal: 20, marginTop: 24,
    padding: 18,
    backgroundColor: COLORS.bgSoft,
    borderRadius: 20,
    borderWidth: 1, borderColor: COLORS.border,
  },
  stepBubble: {
    width: 26, height: 26, borderRadius: 13,
    backgroundColor: "rgba(200,169,107,0.15)",
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: "rgba(200,169,107,0.3)",
  },
  legal: {
    flexDirection: "row",
    alignItems: "flex-start",
    marginHorizontal: 20,
    marginTop: 16,
    padding: 14,
    backgroundColor: COLORS.bgSoft,
    borderRadius: 12,
    borderWidth: 1, borderColor: COLORS.border,
  },
});
