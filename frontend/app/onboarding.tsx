import { View, StyleSheet, Pressable, ScrollView } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { colors, radius, spacing } from "@/src/theme";

const HERO = "https://images.pexels.com/photos/2747599/pexels-photo-2747599.jpeg";

export default function Onboarding() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const choose = (role: "client" | "artisan") => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    router.push({ pathname: "/auth", params: { role } });
  };

  return (
    <View style={styles.container}>
      <View style={styles.heroWrap}>
        <Image source={{ uri: HERO }} style={StyleSheet.absoluteFill} contentFit="cover" />
        <LinearGradient colors={["transparent", "rgba(24,24,27,0.6)", colors.surface]} style={StyleSheet.absoluteFill} />
      </View>

      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + spacing.xl }]} showsVerticalScrollIndicator={false}>
        <View style={styles.badge}>
          <Ionicons name="construct" size={16} color={colors.onSurfaceInverse} />
          <Txt weight="bold" size="sm" color={colors.onSurfaceInverse} style={{ marginLeft: 6 }}>ProConnect</Txt>
        </View>
        <Txt weight="extrabold" size="4xl" style={styles.title}>Le bon artisan,{"\n"}en quelques secondes.</Txt>
        <Txt size="lg" color={colors.muted} style={{ marginTop: spacing.md, marginBottom: spacing["2xl"] }}>
          Plombiers, électriciens, peintres et tous les métiers manuels. Réservez en toute confiance.
        </Txt>

        <Pressable testID="role-client-card" onPress={() => choose("client")} style={({ pressed }) => [styles.card, { opacity: pressed ? 0.9 : 1 }]}>
          <View style={[styles.cardIcon, { backgroundColor: colors.brand }]}>
            <Ionicons name="search" size={22} color={colors.onSurfaceInverse} />
          </View>
          <View style={{ flex: 1 }}>
            <Txt weight="bold" size="lg">{"J'ai besoin d'un professionnel"}</Txt>
            <Txt color={colors.muted} size="sm" style={{ marginTop: 2 }}>Trouvez et réservez un artisan près de chez vous</Txt>
          </View>
          <Ionicons name="chevron-forward" size={20} color={colors.muted} />
        </Pressable>

        <Pressable testID="role-artisan-card" onPress={() => choose("artisan")} style={({ pressed }) => [styles.card, { opacity: pressed ? 0.9 : 1 }]}>
          <View style={[styles.cardIcon, { backgroundColor: colors.success }]}>
            <Ionicons name="hammer" size={22} color={colors.onSurfaceInverse} />
          </View>
          <View style={{ flex: 1 }}>
            <Txt weight="bold" size="lg">Je suis un professionnel</Txt>
            <Txt color={colors.muted} size="sm" style={{ marginTop: 2 }}>Recevez des demandes et développez votre activité</Txt>
          </View>
          <Ionicons name="chevron-forward" size={20} color={colors.muted} />
        </Pressable>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  heroWrap: { height: 320, width: "100%" },
  content: { paddingHorizontal: spacing.lg, marginTop: -70 },
  badge: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.brand, paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, marginBottom: spacing.lg },
  title: { lineHeight: 40 },
  card: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md, gap: spacing.md },
  cardIcon: { width: 48, height: 48, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
});
