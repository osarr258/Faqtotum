import { View, StyleSheet, Pressable, ScrollView } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import Animated, { FadeIn, FadeInDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { colors, radius, spacing, shadow } from "@/src/theme";

const VALUES: { icon: keyof typeof Ionicons.glyphMap; title: string; sub: string }[] = [
  { icon: "sparkles", title: "Diagnostic IA", sub: "Photographiez ou décrivez votre souci." },
  { icon: "pricetags-outline", title: "Prix estimé", sub: "Sachez à quel tarif vous attendre." },
  { icon: "shield-checkmark", title: "Pros vérifiés", sub: "Identité et assurance contrôlées." },
  { icon: "flash", title: "Réservation express", sub: "Le meilleur pro, en quelques secondes." },
];

export default function Onboarding() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const go = (role: "client" | "artisan", intent?: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    router.push({ pathname: "/auth", params: intent ? { role, intent } : { role } });
  };

  return (
    <View style={styles.container}>
      <View style={styles.glow} />
      <LinearGradient colors={["rgba(212,175,106,0.10)", "transparent"]} style={[styles.glowGrad, { pointerEvents: "none" }]} />

      <ScrollView
        contentContainerStyle={[styles.content, { paddingTop: insets.top + spacing.xl, paddingBottom: insets.bottom + spacing["2xl"] }]}
        showsVerticalScrollIndicator={false}
      >
        <Animated.View entering={FadeIn.duration(500)} style={styles.brandRow}>
          <View style={styles.brandDot} />
          <Txt weight="bold" size="base" style={{ letterSpacing: 0.5 }}>ProConnect</Txt>
          <View style={styles.aiPill}>
            <Ionicons name="sparkles" size={11} color={colors.brand} />
            <Txt weight="bold" size="sm" color={colors.brand} style={{ marginLeft: 4 }}>IA</Txt>
          </View>
        </Animated.View>

        <Animated.View entering={FadeInDown.delay(80).duration(600)}>
          <Txt weight="extrabold" size="4xl" style={styles.title}>Comment pouvons-nous vous aider aujourd&apos;hui ?</Txt>
          <Txt size="lg" color={colors.onSurfaceTertiary} style={styles.subtitle}>
            Décrivez votre problème en quelques secondes. Notre IA trouve le meilleur professionnel vérifié, estime le prix et réserve l&apos;intervention.
          </Txt>
        </Animated.View>

        <Animated.View entering={FadeInDown.delay(200).duration(600)}>
          <Pressable
            testID="role-client-card"
            onPress={() => go("client", "problem")}
            android_ripple={{ color: "rgba(0,0,0,0.12)" }}
            style={({ pressed }) => [styles.primaryCta, { transform: [{ scale: pressed ? 0.985 : 1 }] }]}
          >
            <View style={styles.primaryIcon}><Ionicons name="flame" size={22} color={colors.onBrand} /></View>
            <View style={{ flex: 1 }}>
              <Txt weight="extrabold" size="lg" color={colors.onBrand}>J&apos;ai un problème</Txt>
              <Txt size="sm" color="#4A3A12">Dépannage, panne ou urgence</Txt>
            </View>
            <Ionicons name="arrow-forward" size={20} color={colors.onBrand} />
          </Pressable>
        </Animated.View>

        <Animated.View entering={FadeInDown.delay(280).duration(600)}>
          <Pressable
            testID="role-project-card"
            onPress={() => go("client", "project")}
            android_ripple={{ color: "rgba(255,255,255,0.06)" }}
            style={({ pressed }) => [styles.secondaryCta, { opacity: pressed ? 0.85 : 1 }]}
          >
            <View style={styles.secondaryIcon}><Ionicons name="home-outline" size={20} color={colors.onSurface} /></View>
            <View style={{ flex: 1 }}>
              <Txt weight="bold" size="lg">Planifier mon projet</Txt>
              <Txt size="sm" color={colors.muted}>Rénovation, construction, travaux programmés</Txt>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.muted} />
          </Pressable>
        </Animated.View>

        <Animated.View entering={FadeInDown.delay(360).duration(600)} style={styles.valuesGrid}>
          {VALUES.map((v, i) => (
            <Animated.View key={v.title} entering={FadeInDown.delay(440 + i * 90).duration(550)} style={styles.valueCard}>
              <View style={styles.valueIcon}><Ionicons name={v.icon} size={20} color={colors.brand} /></View>
              <Txt weight="bold" size="base" style={{ marginTop: spacing.md }}>{v.title}</Txt>
              <Txt size="sm" color={colors.muted} style={{ marginTop: 2, lineHeight: 18 }}>{v.sub}</Txt>
            </Animated.View>
          ))}
        </Animated.View>

        <Animated.View entering={FadeIn.delay(820).duration(500)}>
          <Pressable
            testID="role-artisan-card"
            onPress={() => go("artisan")}
            android_ripple={{ color: "rgba(255,255,255,0.06)" }}
            style={({ pressed }) => [styles.proCta, { opacity: pressed ? 0.7 : 1 }]}
          >
            <Ionicons name="briefcase-outline" size={18} color={colors.onSurface} />
            <Txt weight="bold" size="base" style={{ marginLeft: spacing.sm }}>Je suis un professionnel</Txt>
          </Pressable>
        </Animated.View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  glow: { position: "absolute", top: -160, alignSelf: "center", width: 420, height: 420, borderRadius: 210, backgroundColor: "rgba(212,175,106,0.16)" },
  glowGrad: { position: "absolute", top: 0, left: 0, right: 0, height: 360 },
  content: { paddingHorizontal: spacing.lg },
  brandRow: { flexDirection: "row", alignItems: "center", marginBottom: spacing["2xl"] },
  brandDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.brand, marginRight: spacing.sm },
  aiPill: { flexDirection: "row", alignItems: "center", marginLeft: spacing.sm, backgroundColor: colors.brand + "1A", paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: radius.pill },
  title: { lineHeight: 42, letterSpacing: -0.5 },
  subtitle: { marginTop: spacing.md, marginBottom: spacing.xl, lineHeight: 24 },
  primaryCta: { flexDirection: "row", alignItems: "center", backgroundColor: colors.brand, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md, marginBottom: spacing.md, ...shadow.card },
  primaryIcon: { width: 46, height: 46, borderRadius: radius.md, backgroundColor: "rgba(0,0,0,0.12)", alignItems: "center", justifyContent: "center" },
  secondaryCta: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md, marginBottom: spacing.xl },
  secondaryIcon: { width: 46, height: 46, borderRadius: radius.md, backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  valuesGrid: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" },
  valueCard: { width: "48.5%", backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md },
  valueIcon: { width: 40, height: 40, borderRadius: radius.md, backgroundColor: colors.brand + "1A", alignItems: "center", justifyContent: "center" },
  proCta: { flexDirection: "row", alignItems: "center", justifyContent: "center", marginTop: spacing.sm, paddingVertical: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.borderStrong },
});
