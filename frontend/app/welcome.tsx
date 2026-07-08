/**
 * Auxora — Cinematic Welcome Screen
 * =========================================================
 * ONE seamless immersive fullscreen experience.
 * - 3 AI-generated hero images with Ken Burns pan/zoom
 * - Cross-fade loop (~21s total, invisible reset)
 * - Golden particles overlay
 * - Text sequence per scene
 * - Buttons appear at 8s and stay fixed forever
 */
import React, { useEffect, useMemo, useState } from "react";
import { View, StyleSheet, Pressable, Dimensions, Platform } from "react-native";
import { Image } from "expo-image";
import { BlurView } from "expo-blur";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withRepeat,
  withDelay,
  withSequence,
  Easing,
} from "react-native-reanimated";
import { Txt } from "@/src/components/ui";

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get("window");

const COLORS = {
  black: "#0A0A0C",
  gold: "#C8A96B",
  goldSoft: "#D4BB86",
  offWhite: "#F5F5F5",
};

const HEROES = [
  require("@/assets/images/auxora_hero_1.png"),
  require("@/assets/images/auxora_hero_2.png"),
  require("@/assets/images/auxora_hero_3.png"),
];

const SCENES = [
  { title: "Un problème chez vous ?", subtitle: "Décrivez-le simplement.\nAuxora s'occupe du reste." },
  { title: "Le bon professionnel.\nÀ chaque fois.", subtitle: "Notre IA sélectionne le meilleur artisan vérifié pour votre besoin." },
  { title: "Réservez. Payez.\nSoyez tranquille.", subtitle: "Tout est sécurisé.\nTout est suivi.\nTout est garanti." },
];

// Timing (ms)
const SCENE_MS = 7000;
const FADE_MS = 1400;
const LOOP_MS = SCENE_MS * 3; // 21 000 ms

const T_LOGO_IN = 1800;
const T_BUTTONS_IN = 8000;

const PARTICLE_COUNT = 22;

// ---------------------------------------------------------------
// Per-layer hero: own opacity + own Ken-Burns loop
// ---------------------------------------------------------------
function HeroLayer({ index }: { index: number }) {
  const opacity = useSharedValue(index === 0 ? 1 : 0);
  const scale = useSharedValue(1.05);
  const tx = useSharedValue(-6);
  const ty = useSharedValue(-4);

  useEffect(() => {
    const holdMs = SCENE_MS - FADE_MS;
    const restMs = LOOP_MS - FADE_MS - holdMs;

    const opacitySeq = withSequence(
      withTiming(1, { duration: FADE_MS, easing: Easing.inOut(Easing.quad) }),
      withTiming(1, { duration: holdMs }),
      withTiming(0, { duration: FADE_MS, easing: Easing.inOut(Easing.quad) }),
      withTiming(0, { duration: Math.max(0, restMs - FADE_MS) })
    );

    if (index === 0) {
      const firstLoop = withSequence(
        withTiming(1, { duration: holdMs }),
        withTiming(0, { duration: FADE_MS, easing: Easing.inOut(Easing.quad) }),
        withTiming(0, { duration: LOOP_MS - holdMs - FADE_MS })
      );
      opacity.value = withSequence(
        firstLoop,
        withRepeat(opacitySeq, -1, false)
      );
    } else {
      opacity.value = withDelay(
        index * SCENE_MS,
        withRepeat(opacitySeq, -1, false)
      );
    }

    // Ken Burns
    const kenSeq = withSequence(
      withTiming(1.05, { duration: 0 }),
      withTiming(1.18, { duration: SCENE_MS, easing: Easing.inOut(Easing.quad) }),
      withTiming(1.05, { duration: LOOP_MS - SCENE_MS })
    );
    scale.value = withDelay(index * SCENE_MS, withRepeat(kenSeq, -1, false));

    const panSeq = withSequence(
      withTiming(-8, { duration: 0 }),
      withTiming(8, { duration: SCENE_MS, easing: Easing.inOut(Easing.quad) }),
      withTiming(-8, { duration: LOOP_MS - SCENE_MS })
    );
    tx.value = withDelay(index * SCENE_MS, withRepeat(panSeq, -1, false));

    const panYSeq = withSequence(
      withTiming(-6, { duration: 0 }),
      withTiming(6, { duration: SCENE_MS, easing: Easing.inOut(Easing.quad) }),
      withTiming(-6, { duration: LOOP_MS - SCENE_MS })
    );
    ty.value = withDelay(index * SCENE_MS, withRepeat(panYSeq, -1, false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const style = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateX: tx.value }, { translateY: ty.value }, { scale: scale.value }],
  }));

  return (
    <Animated.View style={[StyleSheet.absoluteFill, style]} pointerEvents="none">
      <Image
        source={HEROES[index]}
        style={StyleSheet.absoluteFill}
        contentFit="cover"
        transition={0}
        cachePolicy="memory-disk"
        priority="high"
      />
    </Animated.View>
  );
}

// ---------------------------------------------------------------
// Golden particle
// ---------------------------------------------------------------
function Particle({ seed }: { seed: number }) {
  const y = useSharedValue(SCREEN_H + 40);
  const x = useSharedValue(Math.random() * SCREEN_W);
  const opacity = useSharedValue(0);
  const size = 2 + (seed % 5);

  useEffect(() => {
    const duration = 9000 + ((seed * 137) % 6000);
    const delay = (seed * 313) % 8000;
    const drift = ((seed % 7) - 3) * 40;
    const startX = Math.random() * SCREEN_W;

    x.value = startX;
    y.value = SCREEN_H + 30;

    y.value = withDelay(
      delay,
      withRepeat(
        withSequence(
          withTiming(-30, { duration, easing: Easing.linear }),
          withTiming(SCREEN_H + 30, { duration: 0 })
        ),
        -1,
        false
      )
    );
    x.value = withDelay(
      delay,
      withRepeat(
        withSequence(
          withTiming(startX + drift, { duration: duration / 2, easing: Easing.inOut(Easing.ease) }),
          withTiming(startX - drift, { duration: duration / 2, easing: Easing.inOut(Easing.ease) })
        ),
        -1,
        true
      )
    );
    opacity.value = withDelay(
      delay,
      withRepeat(
        withSequence(
          withTiming(0.9, { duration: duration * 0.25 }),
          withTiming(0.4, { duration: duration * 0.5 }),
          withTiming(0, { duration: duration * 0.25 })
        ),
        -1,
        false
      )
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const style = useAnimatedStyle(() => ({
    transform: [{ translateX: x.value }, { translateY: y.value }],
    opacity: opacity.value,
  }));

  return (
    <Animated.View
      pointerEvents="none"
      style={[
        {
          position: "absolute",
          width: size,
          height: size,
          borderRadius: size,
          backgroundColor: COLORS.goldSoft,
          shadowColor: COLORS.gold,
          shadowOpacity: 0.9,
          shadowRadius: size * 2,
          shadowOffset: { width: 0, height: 0 },
        },
        style,
      ]}
    />
  );
}

// ---------------------------------------------------------------
// Scene-cycling text
// ---------------------------------------------------------------
function SceneText({ sceneIdx }: { sceneIdx: number }) {
  const insets = useSafeAreaInsets();
  const titleOpacity = useSharedValue(0);
  const titleY = useSharedValue(20);
  const subOpacity = useSharedValue(0);
  const subY = useSharedValue(16);

  useEffect(() => {
    titleOpacity.value = 0;
    titleY.value = 20;
    subOpacity.value = 0;
    subY.value = 16;

    titleOpacity.value = withDelay(200, withTiming(1, { duration: 900, easing: Easing.out(Easing.cubic) }));
    titleY.value = withDelay(200, withTiming(0, { duration: 900, easing: Easing.out(Easing.cubic) }));
    subOpacity.value = withDelay(1200, withTiming(1, { duration: 900, easing: Easing.out(Easing.cubic) }));
    subY.value = withDelay(1200, withTiming(0, { duration: 900, easing: Easing.out(Easing.cubic) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneIdx]);

  const titleStyle = useAnimatedStyle(() => ({
    opacity: titleOpacity.value,
    transform: [{ translateY: titleY.value }],
  }));
  const subStyle = useAnimatedStyle(() => ({
    opacity: subOpacity.value,
    transform: [{ translateY: subY.value }],
  }));

  const scene = SCENES[sceneIdx];

  return (
    <>
      <Animated.View
        style={[styles.titleLayer, { bottom: insets.bottom + 290 }, titleStyle]}
        pointerEvents="none"
      >
        <Txt weight="extrabold" size="4xl" style={styles.title}>
          {scene.title}
        </Txt>
      </Animated.View>
      <Animated.View
        style={[styles.subLayer, { bottom: insets.bottom + 230 }, subStyle]}
        pointerEvents="none"
      >
        <Txt size="base" style={styles.subtitle}>
          {scene.subtitle}
        </Txt>
      </Animated.View>
    </>
  );
}

// ---------------------------------------------------------------
// Main Welcome Screen
// ---------------------------------------------------------------
export default function Welcome() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [sceneIdx, setSceneIdx] = useState(0);
  const buttonsY = useSharedValue(80);
  const buttonsOpacity = useSharedValue(0);
  const logoOpacity = useSharedValue(0);

  useEffect(() => {
    const iv = setInterval(() => {
      setSceneIdx((s) => (s + 1) % 3);
    }, SCENE_MS);

    logoOpacity.value = withDelay(T_LOGO_IN, withTiming(1, { duration: 1200, easing: Easing.out(Easing.cubic) }));
    buttonsY.value = withDelay(T_BUTTONS_IN, withTiming(0, { duration: 1400, easing: Easing.out(Easing.cubic) }));
    buttonsOpacity.value = withDelay(T_BUTTONS_IN, withTiming(1, { duration: 1400, easing: Easing.out(Easing.quad) }));

    return () => clearInterval(iv);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const buttonsStyle = useAnimatedStyle(() => ({
    opacity: buttonsOpacity.value,
    transform: [{ translateY: buttonsY.value }],
  }));
  const logoStyle = useAnimatedStyle(() => ({ opacity: logoOpacity.value }));

  const particles = useMemo(() => Array.from({ length: PARTICLE_COUNT }, (_, i) => i + 1), []);

  const go = (path: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    router.push(path as any);
  };

  return (
    <View style={styles.container}>
      <HeroLayer index={0} />
      <HeroLayer index={1} />
      <HeroLayer index={2} />

      <LinearGradient
        colors={["rgba(10,10,12,0.55)", "rgba(10,10,12,0.10)", "rgba(10,10,12,0.45)", "rgba(10,10,12,0.95)"]}
        locations={[0, 0.35, 0.62, 1]}
        style={StyleSheet.absoluteFill}
        pointerEvents="none"
      />

      <View pointerEvents="none" style={StyleSheet.absoluteFill}>
        {particles.map((s) => <Particle key={s} seed={s} />)}
      </View>

      <Animated.View style={[styles.logoRow, { top: insets.top + 24 }, logoStyle]} pointerEvents="none">
        <View style={styles.logoDot} />
        <Txt weight="extrabold" size="lg" style={styles.logoText}>AUXORA</Txt>
      </Animated.View>

      <SceneText sceneIdx={sceneIdx} />

      <Animated.View style={[styles.buttonsWrap, { paddingBottom: insets.bottom + 24 }, buttonsStyle]}>
        {Platform.OS !== "web" ? (
          <BlurView intensity={30} tint="dark" style={styles.blurBar} pointerEvents="none" />
        ) : (
          <View style={[styles.blurBar, { backgroundColor: "rgba(10,10,12,0.55)" }]} pointerEvents="none" />
        )}

        <Pressable
          testID="cta-signup"
          onPress={() => go("/auth")}
          style={({ pressed }) => [styles.primary, pressed && { opacity: 0.85, transform: [{ scale: 0.98 }] }]}
        >
          <Txt weight="bold" size="lg" color={COLORS.black} style={{ letterSpacing: 0.3 }}>
            Créer un compte
          </Txt>
        </Pressable>

        <Pressable
          testID="cta-login"
          onPress={() => go("/auth")}
          style={({ pressed }) => [styles.secondary, pressed && { opacity: 0.7 }]}
        >
          <Txt weight="semibold" size="base" color={COLORS.offWhite} style={{ letterSpacing: 0.3 }}>
            Se connecter
          </Txt>
        </Pressable>

        <Pressable
          testID="cta-discover"
          onPress={() => go("/onboarding")}
          style={({ pressed }) => [styles.tertiary, pressed && { opacity: 0.6 }]}
        >
          <Txt weight="medium" size="sm" color={COLORS.goldSoft} style={{ letterSpacing: 0.5 }}>
            Découvrir Auxora  →
          </Txt>
        </Pressable>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.black, overflow: "hidden" },
  logoRow: {
    position: "absolute",
    left: 0,
    right: 0,
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "center",
    gap: 10,
  },
  logoDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: COLORS.gold,
    shadowColor: COLORS.gold,
    shadowOpacity: 0.9,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 0 },
  },
  logoText: {
    color: COLORS.offWhite,
    letterSpacing: 6,
    textTransform: "uppercase",
    fontSize: 15,
  },
  titleLayer: {
    position: "absolute",
    left: 24,
    right: 24,
    alignItems: "flex-start",
  },
  subLayer: {
    position: "absolute",
    left: 24,
    right: 24,
    alignItems: "flex-start",
  },
  title: {
    color: COLORS.offWhite,
    fontSize: 34,
    lineHeight: 40,
    letterSpacing: -0.5,
    textShadowColor: "rgba(0,0,0,0.55)",
    textShadowRadius: 12,
  },
  subtitle: {
    color: "rgba(245,245,245,0.85)",
    fontSize: 15,
    lineHeight: 22,
    letterSpacing: 0.1,
    textShadowColor: "rgba(0,0,0,0.5)",
    textShadowRadius: 8,
  },
  buttonsWrap: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    paddingHorizontal: 24,
    paddingTop: 24,
    gap: 12,
  },
  blurBar: {
    ...StyleSheet.absoluteFillObject,
    top: -40,
  },
  primary: {
    backgroundColor: COLORS.gold,
    borderRadius: 22,
    paddingVertical: 18,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: COLORS.gold,
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.35,
    shadowRadius: 20,
    elevation: 6,
  },
  secondary: {
    borderWidth: 1,
    borderColor: "rgba(245,245,245,0.35)",
    borderRadius: 22,
    paddingVertical: 16,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(255,255,255,0.04)",
  },
  tertiary: {
    alignItems: "center",
    paddingVertical: 10,
    marginTop: 2,
  },
});
