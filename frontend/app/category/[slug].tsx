import { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, FlatList, Pressable, ScrollView, ActivityIndicator, TextInput } from "react-native";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Location from "expo-location";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, EmptyState, Avatar } from "@/src/components/ui";
import FiltersModal, { Filters } from "@/src/components/FiltersModal";
import ArtisanMap from "@/src/components/ArtisanMap";
import { api } from "@/src/api";
import { colors, font, fontSize, radius, spacing } from "@/src/theme";

type Category = { slug: string; name: string; icon: string };
type Artisan = { artisan_id: string; name: string; title: string; city: string; hourly_rate: number; rating: number; reviews_count: number; photo?: string; trade_name: string; distance_km?: number | null; lat?: number | null; lng?: number | null };

export default function CategoryList() {
  const params = useLocalSearchParams<{ slug: string; q?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const initialSlug = params.slug === "all" ? "" : (params.slug || "");
  const [categories, setCategories] = useState<Category[]>([]);
  const [selected, setSelected] = useState<string>(initialSlug);
  const [query, setQuery] = useState<string>(params.q || "");
  const [artisans, setArtisans] = useState<Artisan[]>([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState<Filters>({});
  const [showFilters, setShowFilters] = useState(false);
  const [viewMode, setViewMode] = useState<"list" | "map">("list");
  const [userLocation, setUserLocation] = useState<{ lat: number; lng: number } | null>(null);
  const [locError, setLocError] = useState("");

  useEffect(() => { api<Category[]>("/categories", { auth: false }).then(setCategories).catch(() => {}); }, []);

  const ensureLocation = useCallback(async () => {
    const perm = await Location.getForegroundPermissionsAsync();
    let granted = perm.status === "granted";
    if (!granted && perm.canAskAgain) {
      const req = await Location.requestForegroundPermissionsAsync();
      granted = req.status === "granted";
    }
    if (!granted) { setLocError("Activez la localisation dans les réglages pour trier par proximité."); return null; }
    setLocError("");
    const pos = await Location.getCurrentPositionAsync({});
    const loc = { lat: pos.coords.latitude, lng: pos.coords.longitude };
    setUserLocation(loc);
    return loc;
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs: string[] = [];
      if (selected) qs.push(`category=${selected}`);
      if (query.trim()) qs.push(`q=${encodeURIComponent(query.trim())}`);
      if (filters.maxRate) qs.push(`max_rate=${filters.maxRate}`);
      if (filters.minRating) qs.push(`min_rating=${filters.minRating}`);
      if (filters.available) qs.push(`available=true`);
      if (filters.nearMe || filters.sort === "distance") {
        const loc = userLocation || (await ensureLocation());
        if (loc) {
          qs.push(`lat=${loc.lat}`); qs.push(`lng=${loc.lng}`);
          if (filters.nearMe) qs.push(`radius=150`);
        }
      }
      if (filters.sort) qs.push(`sort=${filters.sort}`);
      const data = await api<Artisan[]>(`/artisans${qs.length ? "?" + qs.join("&") : ""}`, { auth: false });
      setArtisans(data);
    } catch {}
    setLoading(false);
  }, [selected, query, filters, userLocation, ensureLocation]);

  useEffect(() => { load(); }, [load]);

  const activeFilterCount = [filters.maxRate, filters.minRating, filters.available, filters.nearMe, filters.sort].filter(Boolean).length;

  const title = selected ? categories.find((c) => c.slug === selected)?.name || "Artisans" : "Tous les artisans";

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <View style={styles.headerRow}>
          <Pressable testID="back-button" onPress={() => router.back()} style={styles.iconBtn}>
            <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
          </Pressable>
          <Txt weight="bold" size="lg" style={{ flex: 1, marginLeft: spacing.sm }} numberOfLines={1}>{title}</Txt>
          <Pressable testID="toggle-view" onPress={() => setViewMode(viewMode === "list" ? "map" : "list")} style={styles.iconBtn}>
            <Ionicons name={viewMode === "list" ? "map-outline" : "list-outline"} size={20} color={colors.onSurface} />
          </Pressable>
          <Pressable testID="open-filters" onPress={() => setShowFilters(true)} style={[styles.iconBtn, { marginLeft: spacing.sm }]}>
            <Ionicons name="options-outline" size={20} color={colors.onSurface} />
            {activeFilterCount > 0 && <View style={styles.badge}><Txt size="sm" color={colors.onSurfaceInverse} weight="bold">{activeFilterCount}</Txt></View>}
          </Pressable>
        </View>

        <View style={styles.searchBar}>
          <Ionicons name="search" size={18} color={colors.muted} />
          <TextInput
            testID="list-search-input"
            placeholder="Rechercher…"
            placeholderTextColor={colors.muted}
            value={query}
            onChangeText={setQuery}
            style={styles.searchInput}
          />
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
          <Chip label="Tous" active={selected === ""} onPress={() => setSelected("")} testID="chip-all" />
          {categories.map((c) => (
            <Chip key={c.slug} label={c.name} active={selected === c.slug} onPress={() => setSelected(c.slug)} testID={`chip-${c.slug}`} />
          ))}
        </ScrollView>
      </View>

      {locError ? <Txt color={colors.error} size="sm" style={{ paddingHorizontal: spacing.lg, paddingTop: spacing.sm }}>{locError}</Txt> : null}
      {loading ? (
        <ActivityIndicator color={colors.brand} style={{ marginTop: spacing["2xl"] }} />
      ) : viewMode === "map" ? (
        <ArtisanMap artisans={artisans} userLocation={userLocation} onSelect={(aid) => router.push({ pathname: "/artisan/[id]", params: { id: aid } })} />
      ) : (
        <FlatList
          data={artisans}
          keyExtractor={(a) => a.artisan_id}
          contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: spacing["3xl"], flexGrow: 1 }}
          ListEmptyComponent={<EmptyState icon="construct-outline" title="Aucun artisan trouvé" subtitle="Essayez une autre catégorie ou ajustez les filtres." />}
          renderItem={({ item }) => (
            <Pressable
              testID={`artisan-${item.artisan_id}`}
              onPress={() => router.push({ pathname: "/artisan/[id]", params: { id: item.artisan_id } })}
              style={({ pressed }) => [styles.card, { opacity: pressed ? 0.9 : 1 }]}
            >
              {item.photo ? (
                <Image source={{ uri: item.photo }} style={styles.cardImg} contentFit="cover" transition={200} />
              ) : (
                <Avatar name={item.name} size={64} />
              )}
              <View style={{ flex: 1, marginLeft: spacing.md }}>
                <Txt weight="bold" size="base" numberOfLines={1}>{item.name}</Txt>
                <Txt color={colors.muted} size="sm" numberOfLines={1}>{item.title}</Txt>
                <View style={styles.cardMeta}>
                  <Ionicons name="location-outline" size={13} color={colors.muted} />
                  <Txt size="sm" color={colors.muted} style={{ marginLeft: 2 }}>{item.city}</Txt>
                  {item.distance_km != null && <Txt size="sm" color={colors.muted} style={{ marginLeft: 6 }}>· {item.distance_km} km</Txt>}
                </View>
                <View style={styles.cardBottom}>
                  <View style={{ flexDirection: "row", alignItems: "center" }}>
                    <Ionicons name="star" size={13} color={colors.star} />
                    <Txt weight="semibold" size="sm" style={{ marginLeft: 4 }}>{item.rating.toFixed(1)}</Txt>
                    <Txt size="sm" color={colors.muted} style={{ marginLeft: 4 }}>({item.reviews_count})</Txt>
                  </View>
                  <Txt weight="bold" size="base">{item.hourly_rate}€<Txt color={colors.muted} size="sm">/h</Txt></Txt>
                </View>
              </View>
            </Pressable>
          )}
        />
      )}
      <FiltersModal
        visible={showFilters}
        value={filters}
        onApply={(f) => { setFilters(f); setShowFilters(false); }}
        onClose={() => setShowFilters(false)}
      />
    </View>
  );
}

function Chip({ label, active, onPress, testID }: { label: string; active: boolean; onPress: () => void; testID: string }) {
  return (
    <Pressable testID={testID} onPress={onPress} style={[styles.chip, { backgroundColor: active ? colors.brand : colors.surfaceSecondary, borderColor: active ? colors.brand : colors.border }]}>
      <Txt weight="semibold" size="sm" color={active ? colors.onSurfaceInverse : colors.onSurface}>{label}</Txt>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  header: { backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider, paddingBottom: spacing.sm },
  headerRow: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, marginBottom: spacing.sm },
  iconBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  badge: { position: "absolute", top: -4, right: -4, minWidth: 18, height: 18, paddingHorizontal: 4, borderRadius: 9, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  searchBar: { flexDirection: "row", alignItems: "center", marginHorizontal: spacing.lg, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, paddingHorizontal: spacing.lg, height: 46, gap: spacing.sm, marginBottom: spacing.sm },
  searchInput: { flex: 1, fontFamily: font.medium, fontSize: fontSize.base, color: colors.onSurface },
  chipRow: { paddingHorizontal: spacing.lg, gap: spacing.sm, height: 56, alignItems: "center" },
  chip: { height: 36, paddingHorizontal: spacing.lg, borderRadius: radius.pill, borderWidth: 1, alignItems: "center", justifyContent: "center", flexShrink: 0 },
  card: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: spacing.md, marginBottom: spacing.md },
  cardImg: { width: 72, height: 72, borderRadius: radius.md },
  cardMeta: { flexDirection: "row", alignItems: "center", marginTop: 4 },
  cardBottom: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.sm },
});
