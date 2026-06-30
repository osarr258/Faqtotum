import { View, StyleSheet, ScrollView, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Avatar } from "@/src/components/ui";
import { useAuth } from "@/src/context/AuthContext";
import { colors, radius, spacing } from "@/src/theme";

export default function ClientProfile() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const doLogout = async () => {
    await logout();
    router.replace("/onboarding");
  };

  const rows: { icon: any; label: string }[] = [
    { icon: "person-outline", label: "Informations personnelles" },
    { icon: "card-outline", label: "Moyens de paiement" },
    { icon: "notifications-outline", label: "Notifications" },
    { icon: "shield-checkmark-outline", label: "Confidentialité & sécurité" },
    { icon: "help-circle-outline", label: "Aide & support" },
  ];

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"] }} showsVerticalScrollIndicator={false}>
      <Txt weight="extrabold" size="2xl" style={{ paddingHorizontal: spacing.lg, marginBottom: spacing.lg }}>Profil</Txt>

      <View style={styles.userCard}>
        <Avatar name={user?.name} size={56} />
        <View style={{ marginLeft: spacing.md, flex: 1 }}>
          <Txt weight="bold" size="lg">{user?.name}</Txt>
          <Txt color={colors.muted} size="sm">{user?.email}</Txt>
        </View>
      </View>

      <View style={styles.group}>
        {rows.map((r, i) => (
          <Pressable key={r.label} testID={`profile-row-${i}`} style={({ pressed }) => [styles.row, { opacity: pressed ? 0.6 : 1 }, i < rows.length - 1 && styles.rowBorder]}>
            <Ionicons name={r.icon} size={20} color={colors.onSurface} />
            <Txt weight="medium" size="base" style={{ flex: 1, marginLeft: spacing.md }}>{r.label}</Txt>
            <Ionicons name="chevron-forward" size={18} color={colors.muted} />
          </Pressable>
        ))}
      </View>

      <Pressable testID="logout-button" onPress={doLogout} style={({ pressed }) => [styles.logout, { opacity: pressed ? 0.7 : 1 }]}>
        <Ionicons name="log-out-outline" size={20} color={colors.error} />
        <Txt weight="bold" color={colors.error} style={{ marginLeft: spacing.sm }}>Se déconnecter</Txt>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  userCard: { flexDirection: "row", alignItems: "center", marginHorizontal: spacing.lg, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.xl },
  group: { marginHorizontal: spacing.lg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, height: 56 },
  rowBorder: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  logout: { flexDirection: "row", alignItems: "center", justifyContent: "center", marginTop: spacing.xl, marginHorizontal: spacing.lg, height: 54, borderRadius: radius.md, backgroundColor: "#FEE2E2" },
});
