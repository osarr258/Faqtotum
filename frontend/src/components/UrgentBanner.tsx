/**
 * UrgentBanner — bandeau overlay FAQTOTUM affiché en haut de l'écran
 * lorsqu'une nouvelle demande URGENT arrive côté artisan.
 *
 * Comportement :
 *   - Slide in du haut, tap pour ouvrir la demande, tap-close pour dismiss.
 *   - Auto-dismiss après 8 s si aucune action.
 *   - Pulsation rouge subtile pour attirer l'œil sans agresser.
 */
import React, { useEffect, useRef } from "react";
import {
  View,
  StyleSheet,
  Pressable,
  Animated,
  Easing,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { colors, radius, spacing } from "@/src/theme";

type Props = {
  visible: boolean;
  onPress?: () => void;
  onDismiss?: () => void;
  autoDismissMs?: number;
};

export default function UrgentBanner({
  visible,
  onPress,
  onDismiss,
  autoDismissMs = 8000,
}: Props) {
  const insets = useSafeAreaInsets();
  const translateY = useRef(new Animated.Value(-120)).current;
  const pulse = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (visible) {
      Animated.timing(translateY, {
        toValue: 0,
        duration: 260,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }).start();
      const loop = Animated.loop(
        Animated.sequence([
          Animated.timing(pulse, {
            toValue: 0.4,
            duration: 700,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
          Animated.timing(pulse, {
            toValue: 1,
            duration: 700,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
        ]),
      );
      loop.start();
      const t = setTimeout(() => onDismiss?.(), autoDismissMs);
      return () => {
        loop.stop();
        clearTimeout(t);
      };
    } else {
      Animated.timing(translateY, {
        toValue: -120,
        duration: 200,
        easing: Easing.in(Easing.cubic),
        useNativeDriver: true,
      }).start();
    }
  }, [visible, translateY, pulse, autoDismissMs, onDismiss]);

  if (!visible) return null;

  return (
    <Animated.View
      pointerEvents="box-none"
      style={[
        styles.wrap,
        {
          paddingTop: insets.top + 6,
          transform: [{ translateY }],
        },
      ]}
    >
      <Pressable
        testID="urgent-banner"
        onPress={onPress}
        style={({ pressed }) => [
          styles.banner,
          pressed && { opacity: 0.92 },
        ]}
      >
        <Animated.View style={[styles.dot, { opacity: pulse }]} />
        <View style={{ flex: 1, marginLeft: spacing.md }}>
          <Txt
            weight="extrabold"
            size="sm"
            color={colors.textInverse}
            style={{ letterSpacing: 1.5 }}
          >
            NOUVELLE DEMANDE URGENTE
          </Txt>
          <Txt size="sm" color="#FFCCCC" style={{ marginTop: 2 }}>
            Touchez pour voir la demande
          </Txt>
        </View>
        <Pressable
          testID="urgent-banner-dismiss"
          onPress={onDismiss}
          hitSlop={10}
          style={styles.closeBtn}
        >
          <Ionicons name="close" size={18} color={colors.textInverse} />
        </Pressable>
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    zIndex: 100,
    paddingHorizontal: spacing.md,
  },
  banner: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.md,
    backgroundColor: colors.error,
    borderRadius: radius.lg,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 12,
    elevation: 8,
  },
  dot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.textInverse,
  },
  closeBtn: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(255,255,255,0.15)",
  },
});
