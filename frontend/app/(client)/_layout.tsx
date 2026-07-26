/**
 * Auxora V2 — Bottom Navigation
 * 4 icons: AI, Maison, Carte, Profil. No labels by default (only on active).
 */
import React from "react";
import { Tabs } from "expo-router";
import { View, Platform } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useTheme, palette, space } from "@/src/design";
import { hap } from "@/src/design/haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";

function TabIcon({ name, focused }: { name: keyof typeof Ionicons.glyphMap; focused: boolean }) {
  const t = useTheme();
  return (
    <View style={{
      width: 48, height: 32,
      alignItems: "center", justifyContent: "center",
      borderRadius: 999,
      backgroundColor: focused ? t.fg : "transparent",
    }}>
      <Ionicons name={name} size={20} color={focused ? t.bg : t.fg} />
    </View>
  );
}

export default function ClientLayout() {
  const t = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <Tabs
      screenListeners={{ tabPress: () => hap.tap() }}
      screenOptions={{
        headerShown: false,
        tabBarShowLabel: false,
        tabBarStyle: {
          position: "absolute",
          left: space.xl, right: space.xl, bottom: Math.max(insets.bottom, space.md),
          height: 60,
          backgroundColor: t.bgElevated,
          borderRadius: 999,
          borderTopWidth: 0,
          borderWidth: 1,
          borderColor: t.border,
          shadowColor: palette.ink,
          shadowOpacity: 0.12,
          shadowRadius: 24,
          shadowOffset: { width: 0, height: 10 },
          elevation: 12,
          paddingHorizontal: space.md,
          paddingBottom: 0,
          paddingTop: 0,
        },
      }}
    >
      <Tabs.Screen name="index"    options={{ tabBarIcon: ({ focused }) => <TabIcon name={focused ? "sparkles" : "sparkles-outline"} focused={focused} /> }} />
      <Tabs.Screen name="home"     options={{ tabBarIcon: ({ focused }) => <TabIcon name={focused ? "home" : "home-outline"} focused={focused} /> }} />
      <Tabs.Screen name="map"      options={{ tabBarIcon: ({ focused }) => <TabIcon name={focused ? "map" : "map-outline"} focused={focused} /> }} />
      <Tabs.Screen name="profile"  options={{ tabBarIcon: ({ focused }) => <TabIcon name={focused ? "person" : "person-outline"} focused={focused} /> }} />
      {/* Legacy screens kept accessible via AI intents but hidden from the tab bar */}
      <Tabs.Screen name="bookings" options={{ href: null }} />
      <Tabs.Screen name="messages" options={{ href: null }} />
    </Tabs>
  );
}
