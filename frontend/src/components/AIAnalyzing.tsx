import { useEffect, useState } from "react";
import { View, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import Animated, { useSharedValue, useAnimatedStyle, withRepeat, withTiming, withSequence, Easing, FadeIn, FadeOut } from "react-native-reanimated";
import { Txt } from "@/src/components/ui";
import { colors, radius, spacing } from "@/src/theme";

const MESSAGES = [
  "Analyse de votre description…",
  "Détection du type de problème…",
  "Comparaison avec des milliers d'interventions…",
  "Estimation du coût moyen…",
  "Recherche des meilleurs pros à proximité…",
];

export default function AIAnalyzing() {
  const [idx, setIdx] = useState(0);
  const pulse = useSharedValue(1);
  const ring = useSharedValue(0);
  const progress = useSharedValue(0);

  useEffect(() => {
    pulse.value = withRepeat(withSequence(withTiming(1.12, { duration: 700 }), withTiming(1, { duration: 700 })), -1, false);
    ring.value = withRepeat(withTiming(1, { duration: 1600, easing: Easing.out(Easing.ease) }), -1, false);
    progress.value = withTiming(1, { duration: 5200, easing: Easing.inOut(Easing.ease) });
    const t = setInterval(() => setIdx((i) => Math.min(i + 1, MESSAGES.length - 1)), 1050);
    return () => clearInterval(t);
  }, []);

  const pulseStyle = useAnimatedStyle(() => ({ transform: [{ scale: pulse.value }] }));
  const ringStyle = useAnimatedStyle(() => ({ transform: [{ scale: 1 + ring.value * 1.4 }], opacity: 1 - ring.value }));
  const barStyle = useAnimatedStyle(() => ({ width: `${progress.value * 100}%` }));

  return (
    <View style={styles.overlay} testID="ai-analyzing">
      <View style={styles.center}>
        <View style={styles.orbWrap}>
          <Animated.View style={[styles.ring, ringStyle]} />
          <Animated.View style={[styles.orb, pulseStyle]}>
            <Ionicons name="sparkles" size={34} color={colors.onBrand} />
          </Animated.View>
        </View>

        <Txt weight="extrabold" size="xl" style={{ marginTop: spacing["2xl"] }}>Analyse IA en cours</Txt>

        <Animated.View key={idx} entering={FadeIn.duration(300)} exiting={FadeOut.duration(200)} style={{ marginTop: spacing.md, height: 24 }}>
          <Txt color={colors.onSurfaceSecondary} style={{ textAlign: "center" }}>{MESSAGES[idx]}</Txt>
        </Animated.View>

        <View style={styles.barBg}>
          <Animated.View style={[styles.barFill, barStyle]} />
        </View>

        <View style={styles.steps}>
          {MESSAGES.map((_, i) => (
            <View key={i} style={[styles.dot, { backgroundColor: i <= idx ? colors.brand : colors.surfaceTertiary }]} />
          ))}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: { ...StyleSheet.absoluteFillObject, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", zIndex: 50 },
  center: { alignItems: "center", paddingHorizontal: spacing.xl },
  orbWrap: { width: 120, height: 120, alignItems: "center", justifyContent: "center" },
  ring: { position: "absolute", width: 90, height: 90, borderRadius: 45, borderWidth: 2, borderColor: colors.brand },
  orb: { width: 84, height: 84, borderRadius: 42, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  barBg: { width: 240, height: 6, borderRadius: 3, backgroundColor: colors.surfaceTertiary, marginTop: spacing.xl, overflow: "hidden" },
  barFill: { height: 6, borderRadius: 3, backgroundColor: colors.brand },
  steps: { flexDirection: "row", gap: 8, marginTop: spacing.lg },
  dot: { width: 8, height: 8, borderRadius: 4 },
});
