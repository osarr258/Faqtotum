import { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, ScrollView, Pressable, TextInput, RefreshControl, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Avatar } from "@/src/components/ui";
import { useAuth } from "@/src/context/AuthContext";
import { api } from "@/src/api";
import { colors, font, fontSize, radius, spacing, shadow } from "@/src/theme";

type Category = { slug: string; name: string; icon: string };
type Artisan = { artisan_id: string; name: string; title: string; city: string; hourly_rate: number; rating: number; reviews_count: number; photo?: string; trade_name: string; trade_icon: string };

export default function ClientHome() {
  const { user } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [categories, setCategories] = useState<Category[]>([]);
  const [top, setTop] = useState<Artisan[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [cats, tops] = await Promise.all([api<Category[]>("/categories", { auth: false }), api<Artisan[]>("/artisans/top", { auth: false })]);
      setCategories(cats);
      setTop(tops);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const search = () => {
    if (query.trim()) router.push({ pathname: "/category/[slug]", params: { slug: "all", q: query.trim() } });
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView
        contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"] }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
      >
        <View style={styles.header}>
          <View style={{ flex: 1 }}>
            <Txt color={colors.muted} size="sm">Bonjour 👋</Txt>
            <Txt weight="extrabold" size="2xl">{user?.name?.split(" ")[0] || "Bienvenue"}</Txt>
          </View>
          <Avatar name={user?.name} size={44} />
        </View>

        <Pressable testID="problem-button" onPress={() => router.push({ pathname: "/concierge/[id]", params: { id: "new" } })} style={styles.problemBtn}>
          <LinearGradient colors={["#E7C988", "#C9A24B", "#A87B2E"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.problemGrad}>
            <View style={{ flex: 1 }}>
              <View style={styles.aiTag}>
                <Ionicons name="sparkles" size={12} color={colors.onBrand} />
                <Txt weight="bold" size="sm" color={colors.onBrand} style={{ marginLeft: 4 }}>Diagnostic IA</Txt>
              </View>
              <Txt weight="extrabold" size="2xl" color={colors.onBrand} style={{ marginTop: spacing.sm }}>J&apos;ai un problème</Txt>
              <Txt size="sm" color="#3A2E12" style={{ marginTop: 2 }}>Décrivez, photographiez ou parlez — l&apos;IA trouve le meilleur pro.</Txt>
            </View>
            <View style={styles.problemIcon}>
              <Ionicons name="flash" size={28} color={colors.onBrand} />
            </View>
          </LinearGradient>
        </Pressable>

        <View style={styles.searchBar}>
          <Ionicons name="search" size={20} color={colors.muted} />
          <TextInput
            testID="home-search-input"
            placeholder="Rechercher un métier, une ville…"
            placeholderTextColor={colors.muted}
            value={query}
            onChangeText={setQuery}
            onSubmitEditing={search}
            returnKeyType="search"
            style={styles.searchInput}
          />
        </View>

        <Txt weight="bold" size="lg" style={styles.sectionTitle}>Catégories</Txt>
        {loading ? (
          <ActivityIndicator color={colors.brand} style={{ marginTop: spacing.xl }} />
        ) : (
          <View style={styles.grid}>
            {categories.map((c) => (
              <Pressable
                key={c.slug}
                testID={`category-${c.slug}`}
                onPress={() => router.push({ pathname: "/category/[slug]", params: { slug: c.slug } })}
                style={({ pressed }) => [styles.catCard, { opacity: pressed ? 0.85 : 1 }]}
              >
                <View style={styles.catIcon}>
                  <Ionicons name={c.icon as any} size={24} color={colors.onSurface} />
                </View>
                <Txt weight="semibold" size="sm" style={{ marginTop: spacing.sm, textAlign: "center" }} numberOfLines={1}>{c.name}</Txt>
              </Pressable>
            ))}
          </View>
        )}

        <View style={styles.sectionRow}>
          <Txt weight="bold" size="lg">Les mieux notés</Txt>
          <Pressable testID="see-all-top" onPress={() => router.push({ pathname: "/category/[slug]", params: { slug: "all" } })}>
            <Txt weight="semibold" size="sm" color={colors.muted}>Tout voir</Txt>
          </Pressable>
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: spacing.lg, gap: spacing.md }}>
          {top.map((a) => (
            <Pressable
              key={a.artisan_id}
              testID={`top-artisan-${a.artisan_id}`}
              onPress={() => router.push({ pathname: "/artisan/[id]", params: { id: a.artisan_id } })}
              style={styles.topCard}
            >
              <Image source={{ uri: a.photo }} style={styles.topImage} contentFit="cover" transition={200} />
              <LinearGradient colors={["transparent", "rgba(24,24,27,0.85)"]} style={styles.topScrim} />
              <View style={styles.topInfo}>
                <View style={styles.tradePill}>
                  <Txt weight="semibold" size="sm" color={colors.textInverse}>{a.trade_name}</Txt>
                </View>
                <Txt weight="bold" size="lg" color={colors.textInverse} numberOfLines={1}>{a.name}</Txt>
                <View style={{ flexDirection: "row", alignItems: "center", marginTop: 2 }}>
                  <Ionicons name="star" size={13} color={colors.star} />
                  <Txt weight="semibold" size="sm" color={colors.textInverse} style={{ marginLeft: 4 }}>{a.rating.toFixed(1)}</Txt>
                  <Txt size="sm" color="#D4D4D8" style={{ marginLeft: 8 }}>{a.hourly_rate}€/h</Txt>
                </View>
              </View>
            </Pressable>
          ))}
        </ScrollView>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, marginBottom: spacing.lg },
  problemBtn: { marginHorizontal: spacing.lg, marginBottom: spacing.lg, borderRadius: radius.lg, overflow: "hidden", ...shadow.card },
  problemGrad: { flexDirection: "row", alignItems: "center", padding: spacing.lg },
  aiTag: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", backgroundColor: "rgba(255,255,255,0.35)", paddingHorizontal: spacing.sm, paddingVertical: 3, borderRadius: radius.pill },
  problemIcon: { width: 52, height: 52, borderRadius: 26, backgroundColor: "rgba(255,255,255,0.3)", alignItems: "center", justifyContent: "center", marginLeft: spacing.md },
  searchBar: { flexDirection: "row", alignItems: "center", marginHorizontal: spacing.lg, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, paddingHorizontal: spacing.lg, height: 52, gap: spacing.sm },
  searchInput: { flex: 1, fontFamily: font.medium, fontSize: fontSize.base, color: colors.onSurface },
  sectionTitle: { paddingHorizontal: spacing.lg, marginTop: spacing.xl, marginBottom: spacing.md },
  sectionRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, marginTop: spacing.xl, marginBottom: spacing.md },
  grid: { flexDirection: "row", flexWrap: "wrap", paddingHorizontal: spacing.lg - spacing.xs, gap: 0 },
  catCard: { width: "33.333%", padding: spacing.xs, alignItems: "center", marginBottom: spacing.sm },
  catIcon: { width: "100%", aspectRatio: 1.3, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  topCard: { width: 210, height: 260, borderRadius: radius.lg, overflow: "hidden", ...shadow.card },
  topImage: { width: "100%", height: "100%" },
  topScrim: { position: "absolute", left: 0, right: 0, bottom: 0, height: "65%" },
  topInfo: { position: "absolute", left: spacing.md, right: spacing.md, bottom: spacing.md },
  tradePill: { alignSelf: "flex-start", backgroundColor: "rgba(255,255,255,0.2)", paddingHorizontal: spacing.sm, paddingVertical: 3, borderRadius: radius.pill, marginBottom: spacing.xs },
});
