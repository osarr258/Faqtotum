/**
 * Auxora Design System — Primitive components.
 * Use ONLY these across the redesigned app.
 */
import React, { useRef } from "react";
import {
  View, Text as RNText, TextStyle, ViewStyle, StyleProp,
  Pressable, PressableProps, StyleSheet, Animated, Easing, ActivityIndicator,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "./ThemeProvider";
import { type as typeTokens, radius, space, motion } from "./tokens";
import { hap } from "./haptics";

type TypeVariant = keyof typeof typeTokens;

export function Text({
  variant = "body",
  tone = "fg",
  style,
  children,
  numberOfLines,
  align,
}: {
  variant?: TypeVariant;
  tone?: "fg" | "fgMuted" | "fgSubtle" | "brand" | "danger" | "success";
  style?: StyleProp<TextStyle>;
  children: React.ReactNode;
  numberOfLines?: number;
  align?: "left" | "center" | "right";
}) {
  const t = useTheme();
  const v = typeTokens[variant];
  return (
    <RNText
      numberOfLines={numberOfLines}
      allowFontScaling
      style={[
        {
          // Auxora typeface: Plus Jakarta Sans (Inter-adjacent geometric sans
          // already loaded at boot). We map weight → variant filename.
          fontFamily:
            v.weight === "700" ? "Jakarta700" :
            v.weight === "600" ? "Jakarta600" :
            v.weight === "500" ? "Jakarta500" :
            "Jakarta400",
          fontSize: v.size,
          lineHeight: v.line,
          letterSpacing: v.tracking,
          color: (t as any)[tone],
          textAlign: align,
        },
        style,
      ]}
    >
      {children}
    </RNText>
  );
}

export function Card({
  children, style, padded = true, elevated = false,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  padded?: boolean;
  elevated?: boolean;
}) {
  const t = useTheme();
  return (
    <View
      style={[
        {
          backgroundColor: elevated ? t.bgElevated : t.bgAlt,
          borderRadius: radius.lg,
          borderWidth: 1,
          borderColor: t.border,
          padding: padded ? space.lg : 0,
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}

type BtnVariant = "primary" | "secondary" | "ghost" | "danger" | "floating" | "icon";

export function Button({
  title, onPress, variant = "primary", icon, iconRight, loading, disabled, style,
  fullWidth = false,
  size = "md",
  testID,
}: {
  title?: string;
  onPress?: () => void;
  variant?: BtnVariant;
  icon?: keyof typeof Ionicons.glyphMap;
  iconRight?: keyof typeof Ionicons.glyphMap;
  loading?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
  fullWidth?: boolean;
  size?: "sm" | "md" | "lg";
  testID?: string;
}) {
  const t = useTheme();
  const scale = useRef(new Animated.Value(1)).current;

  const bg = {
    primary: t.fg,
    secondary: t.bgAlt,
    ghost: "transparent",
    danger: t.danger,
    floating: t.bgElevated,
    icon: t.bgAlt,
  }[variant];

  const fg = {
    primary: t.bg,
    secondary: t.fg,
    ghost: t.fg,
    danger: "#FFFFFF",
    floating: t.fg,
    icon: t.fg,
  }[variant];

  const h = size === "sm" ? 40 : size === "lg" ? 60 : 52;

  const anim = (to: number) =>
    Animated.timing(scale, {
      toValue: to,
      duration: motion.fast,
      easing: Easing.bezier(0.16, 1, 0.3, 1),
      useNativeDriver: true,
    }).start();

  return (
    <Pressable
      testID={testID}
      onPressIn={() => { anim(0.97); hap.tap(); }}
      onPressOut={() => anim(1)}
      onPress={disabled || loading ? undefined : onPress}
      disabled={disabled || loading}
      hitSlop={8}
      style={[
        {
          alignSelf: fullWidth ? "stretch" : "auto",
          opacity: disabled ? 0.5 : 1,
        },
        style,
      ]}
    >
      <Animated.View
        style={[
          {
            height: h,
            paddingHorizontal: variant === "icon" ? 0 : space.xl,
            borderRadius: radius.pill,
            backgroundColor: bg,
            flexDirection: "row",
            alignItems: "center",
            justifyContent: "center",
            gap: 10,
            borderWidth: variant === "secondary" || variant === "ghost" || variant === "floating" ? 1 : 0,
            borderColor: t.border,
            width: variant === "icon" ? h : undefined,
            transform: [{ scale }],
          },
        ]}
      >
        {loading ? (
          <ActivityIndicator color={fg} />
        ) : (
          <>
            {icon ? <Ionicons name={icon} size={18} color={fg} /> : null}
            {title ? (
              <RNText style={{
                fontFamily: "Jakarta600",
                color: fg,
                fontSize: size === "lg" ? 17 : 15,
                letterSpacing: -0.1,
              }}>{title}</RNText>
            ) : null}
            {iconRight ? <Ionicons name={iconRight} size={18} color={fg} /> : null}
          </>
        )}
      </Animated.View>
    </Pressable>
  );
}

export function Chip({
  label, active = false, icon, onPress, testID,
}: {
  label: string;
  active?: boolean;
  icon?: keyof typeof Ionicons.glyphMap;
  onPress?: () => void;
  testID?: string;
}) {
  const t = useTheme();
  return (
    <Pressable
      testID={testID}
      onPress={() => { hap.tap(); onPress?.(); }}
      style={{
        paddingHorizontal: space.md + 2,
        height: 34,
        borderRadius: radius.pill,
        backgroundColor: active ? t.fg : t.bgAlt,
        borderWidth: 1,
        borderColor: active ? t.fg : t.border,
        flexDirection: "row",
        alignItems: "center",
        gap: 6,
      }}
    >
      {icon ? <Ionicons name={icon} size={14} color={active ? t.bg : t.fg} /> : null}
      <RNText style={{
        fontFamily: "Jakarta600",
        fontSize: 13,
        color: active ? t.bg : t.fg,
        letterSpacing: -0.1,
      }}>{label}</RNText>
    </Pressable>
  );
}

export function Divider() {
  const t = useTheme();
  return <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: t.border }} />;
}

export function Row({
  children, style, gap = space.md, wrap = false, center = false,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  gap?: number;
  wrap?: boolean;
  center?: boolean;
}) {
  return (
    <View style={[
      {
        flexDirection: "row",
        alignItems: center ? "center" : "flex-start",
        gap,
        flexWrap: wrap ? "wrap" : "nowrap",
      },
      style,
    ]}>{children}</View>
  );
}

export function Stack({
  children, style, gap = space.md,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  gap?: number;
}) {
  return <View style={[{ gap }, style]}>{children}</View>;
}
