/**
 * Mock Stripe Connect onboarding landing.
 * In mock mode the backend returns a fake URL pointing here.
 * When real Stripe keys are configured, users are redirected to Stripe's real onboarding.
 */
import React, { useEffect, useState } from "react";
import { View, StyleSheet, Pressable, ActivityIndicator } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, { FadeInUp } from "react-native-reanimated";
import { Txt } from "@/src/components/ui";

const COLORS = { bg: "#0B0B0B", bgSoft: "#141416", white: "#FFFFFF", accent: "#C8A96B", secondary: "#B8B8B8", muted: "#6E6E73", border: "#1F1F22" };

export default function MockOnboarding() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ acct?: string }>();
  const [step, setStep] = useState<"intro" | "processing" | "done">("intro");

  useEffect(() => {
    if (step !== "processing") return;
    const t = setTimeout(() => setStep("done"), 1800);
    return () => clearTimeout(t);
  }, [step]);

  return (
    <View style={[styles.container, { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24 }]}>
      <View style={styles.header}>
        <View style={styles.stripeMark}>
          <Txt weight="extrabold" style={{ color: COLORS.white, letterSpacing: 3 }}>STRIPE</Txt>
        </View>
      </View>

      {step === "intro" && (
        <Animated.View entering={FadeInUp.duration(400)} style={styles.card}>
          <Txt weight="extrabold" style={styles.title}>Configurez votre compte</Txt>
          <Txt style={styles.body}>
            Faqtotum utilise Stripe pour vous verser vos paiements en toute sécurité.
            En quelques étapes, vous serez prêt à recevoir vos gains.
          </Txt>
          <View style={styles.checks}>
            <CheckLine label="Vérification d'identité" />
            <CheckLine label="Compte bancaire" />
            <CheckLine label="Signature électronique" />
          </View>
          <View style={styles.mockNotice}>
            <Ionicons name="information-circle-outline" size={14} color={COLORS.muted} />
            <Txt size="sm" style={{ color: COLORS.muted, marginLeft: 6, flex: 1, lineHeight: 18 }}>
              Aperçu Emergent — la vraie page d&apos;onboarding Stripe s&apos;affichera dès que les clés réelles seront fournies.
            </Txt>
          </View>
          <Pressable
            testID="mock-continue"
            onPress={() => setStep("processing")}
            style={({ pressed }) => [styles.primary, pressed && { opacity: 0.85 }]}
          >
            <Txt weight="bold" style={{ color: "#FFF" }}>Continuer vers Stripe</Txt>
          </Pressable>
        </Animated.View>
      )}

      {step === "processing" && (
        <View style={styles.center}>
          <ActivityIndicator color={COLORS.white} size="large" />
          <Txt style={{ color: COLORS.white, marginTop: 16 }}>Configuration en cours…</Txt>
        </View>
      )}

      {step === "done" && (
        <Animated.View entering={FadeInUp.duration(400)} style={styles.card}>
          <View style={styles.doneIcon}>
            <Ionicons name="checkmark" size={32} color="#FFF" />
          </View>
          <Txt weight="extrabold" style={styles.title}>Compte configuré !</Txt>
          <Txt style={styles.body}>
            Votre compte Stripe est prêt. Vous pouvez maintenant recevoir vos paiements.
          </Txt>
          {!!params.acct && (
            <Txt size="sm" style={{ color: COLORS.muted, marginTop: 8 }}>ID compte : {String(params.acct).slice(0, 20)}…</Txt>
          )}
          <Pressable
            testID="mock-return"
            onPress={() => router.replace("/connect")}
            style={({ pressed }) => [styles.primary, pressed && { opacity: 0.85 }]}
          >
            <Txt weight="bold" style={{ color: "#FFF" }}>Retourner sur Faqtotum</Txt>
          </Pressable>
        </Animated.View>
      )}
    </View>
  );
}

function CheckLine({ label }: { label: string }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", marginTop: 10 }}>
      <Ionicons name="checkmark-circle" size={18} color="#635BFF" />
      <Txt style={{ color: COLORS.white, marginLeft: 8 }}>{label}</Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0A2540", paddingHorizontal: 24 },
  header: { alignItems: "center", marginBottom: 24 },
  stripeMark: { paddingHorizontal: 16, paddingVertical: 6, backgroundColor: "#635BFF", borderRadius: 6 },
  card: { backgroundColor: "#FFFFFF12", padding: 24, borderRadius: 20, borderWidth: 1, borderColor: "#FFFFFF20" },
  title: { color: "#FFF", fontSize: 24, marginBottom: 8 },
  body: { color: "#B0B7C3", fontSize: 14, lineHeight: 20 },
  checks: { marginTop: 16 },
  mockNotice: {
    flexDirection: "row",
    alignItems: "flex-start",
    marginTop: 20,
    padding: 12,
    backgroundColor: "rgba(200,169,107,0.1)",
    borderRadius: 10,
    borderWidth: 1, borderColor: "rgba(200,169,107,0.2)",
  },
  primary: {
    backgroundColor: "#635BFF",
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 24,
  },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  doneIcon: {
    width: 60, height: 60, borderRadius: 30,
    backgroundColor: "#00D924",
    alignItems: "center", justifyContent: "center",
    alignSelf: "center", marginBottom: 16,
  },
});
