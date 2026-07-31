/**
 * Faqtotum — Welcome Cinematic (V2)
 * Three-scene infinite loop, no login until end.
 * Minimalist black/white/grey palette — Apple × Stripe aesthetic.
 */
import React, { useEffect, useRef, useState } from "react";
import {
  View, StyleSheet, Animated, Easing, Dimensions, Pressable,
} from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { Text, Button, useTheme, space, motion, palette } from "@/src/design";
import { hap } from "@/src/design/haptics";

const { width: W, height: H } = Dimensions.get("window");

const SCENES = [
  {
    uri: "https://images.unsplash.com/photo-1758915753369-6a33c7bc1d76?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    kicker: "FAQTOTUM",
    title: "Votre maison mérite mieux.",
    sub: "Un foyer entretenu, protégé, valorisé.",
  },
  {
    uri: "https://images.unsplash.com/photo-1511711890176-b3a26e4fb6d1?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    kicker: "DÉCRIVEZ LE PROBLÈME",
    title: "Une fuite. Une panne. Un doute.",
    sub: "L'IA comprend. Instantanément.",
  },
  {
    uri: "https://images.unsplash.com/photo-1659930087003-2d64e33181f7?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    kicker: "LE FUTUR DE LA MAISON",
    title: "Un artisan de confiance. Toujours.",
    sub: "Suivi, garantie, passeport numérique.",
  },
];

const SCENE_MS = 5400;

export default function Welcome() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [i, setI] = useState(0);
  const fade = useRef(new Animated.Value(0)).current;
  const zoom = useRef(new Animated.Value(1)).current;
  const textY = useRef(new Animated.Value(20)).current;
  const textO = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    fade.setValue(0);
    zoom.setValue(1.08);
    textY.setValue(24);
    textO.setValue(0);
    Animated.parallel([
      Animated.timing(fade, { toValue: 1, duration: motion.slow, useNativeDriver: true }),
      Animated.timing(zoom, { toValue: 1, duration: SCENE_MS, easing: Easing.out(Easing.quad), useNativeDriver: true }),
      Animated.sequence([
        Animated.delay(220),
        Animated.parallel([
          Animated.timing(textY, { toValue: 0, duration: motion.slow, easing: Easing.bezier(0.16, 1, 0.3, 1), useNativeDriver: true }),
          Animated.timing(textO, { toValue: 1, duration: motion.slow, useNativeDriver: true }),
        ]),
      ]),
    ]).start();
    const t = setTimeout(() => setI((v) => (v + 1) % SCENES.length), SCENE_MS);
    return () => clearTimeout(t);
  }, [i]);

  const s = SCENES[i];
  const t = useTheme();

  return (
    <View style={{ flex: 1, backgroundColor: palette.ink }}>
      <StatusBar style="light" />
      <Animated.View style={[StyleSheet.absoluteFillObject, { opacity: fade, transform: [{ scale: zoom }] }]}>
        <Image source={{ uri: s.uri }} style={StyleSheet.absoluteFillObject as any} contentFit="cover" transition={400} />
      </Animated.View>
      <LinearGradient
        colors={["rgba(11,11,13,0.15)", "rgba(11,11,13,0.45)", "rgba(11,11,13,0.95)"]}
        locations={[0, 0.55, 1]}
        style={StyleSheet.absoluteFillObject as any}
      />

      {/* Word mark */}
      <View style={{ position: "absolute", top: insets.top + space.xl, left: 0, right: 0, alignItems: "center" }}>
        <Text variant="caption" style={{ color: palette.paper, letterSpacing: 6 }}>FAQTOTUM</Text>
      </View>

      {/* Progress rail */}
      <View style={{ position: "absolute", top: insets.top + space.xl + 26, left: space.xl, right: space.xl, flexDirection: "row", gap: 6 }}>
        {SCENES.map((_, k) => (
          <View key={k} style={{ flex: 1, height: 2, backgroundColor: "rgba(255,255,255,0.18)", borderRadius: 1, overflow: "hidden" }}>
            <Animated.View
              style={{
                height: "100%",
                backgroundColor: palette.paper,
                width: k < i ? "100%" : k === i ? fade.interpolate({ inputRange: [0, 1], outputRange: ["0%", "100%"] }) : "0%",
              }}
            />
          </View>
        ))}
      </View>

      {/* Copy */}
      <Animated.View
        style={{
          position: "absolute",
          bottom: insets.bottom + 180,
          left: space.xl,
          right: space.xl,
          opacity: textO,
          transform: [{ translateY: textY }],
        }}
      >
        <Text variant="caption" style={{ color: "rgba(255,255,255,0.70)", letterSpacing: 3, marginBottom: space.md }}>{s.kicker}</Text>
        <Text variant="hero" style={{ color: palette.paper }}>{s.title}</Text>
        <Text variant="body" style={{ color: "rgba(248,248,245,0.75)", marginTop: space.md }}>{s.sub}</Text>
      </Animated.View>

      {/* Actions */}
      <View style={{ position: "absolute", bottom: insets.bottom + space.xl, left: space.xl, right: space.xl, gap: space.md }}>
        <Pressable
          testID="welcome-signup"
          onPress={() => { hap.firm(); router.push("/auth?mode=signup"); }}
          style={{
            height: 56,
            borderRadius: 999,
            backgroundColor: palette.paper,
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Text variant="h3" style={{ color: palette.ink }}>Créer un compte</Text>
        </Pressable>
        <Pressable
          testID="welcome-login"
          onPress={() => { hap.tap(); router.push("/auth?mode=login"); }}
          style={{
            height: 56,
            borderRadius: 999,
            borderWidth: 1,
            borderColor: "rgba(248,248,245,0.35)",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Text variant="h3" style={{ color: palette.paper }}>J'ai déjà un compte</Text>
        </Pressable>
      </View>
    </View>
  );
}
