import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Platform } from "react-native";
import { colors, font } from "@/src/theme";

/**
 * FAQTOTUM artisan tabs — 5 destinations principales.
 *
 *   Accueil (index)   — Hub avec urgent, nouvelles demandes, aujourd'hui
 *   Missions (live)   — Segment À traiter / En cours / Historique
 *   Agenda            — Vue semaine + créneaux
 *   Messages          — Conversations
 *   Profil            — Profil pro + accès abonnement
 *
 * L'onglet Abonnement est masqué du tab bar mais reste routable
 * (`/(artisan)/subscription`) — accès depuis le Profil.
 */
export default function ArtisanLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brand,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          height: Platform.OS === "ios" ? 88 : 64,
          paddingTop: 8,
        },
        tabBarLabelStyle: { fontFamily: font.semibold, fontSize: 11 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Accueil",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="home-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="live"
        options={{
          title: "Missions",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="briefcase-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="agenda"
        options={{
          title: "Agenda",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="calendar-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="messages"
        options={{
          title: "Messages",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="chatbubble-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: "Profil",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="person-outline" size={size} color={color} />
          ),
        }}
      />
      {/* Abonnement — route existante, masquée du tab bar (accès depuis Profil). */}
      <Tabs.Screen
        name="subscription"
        options={{
          href: null,
        }}
      />
    </Tabs>
  );
}
