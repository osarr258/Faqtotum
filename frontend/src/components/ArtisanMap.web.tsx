import { View, StyleSheet, Pressable, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Txt } from "@/src/components/ui";
import { colors, radius, spacing } from "@/src/theme";

type Artisan = { artisan_id: string; name: string; trade_name: string; hourly_rate: number; city?: string; distance_km?: number | null };

// react-native-maps has no web support; render a lightweight clickable fallback.
export default function ArtisanMap({ artisans, onSelect }: {
  artisans: Artisan[];
  userLocation?: { lat: number; lng: number } | null;
  onSelect: (id: string) => void;
}) {
  return (
    <View style={styles.container}>
      <View style={styles.banner}>
        <Ionicons name="map" size={18} color={colors.muted} />
        <Txt size="sm" color={colors.muted} style={{ marginLeft: spacing.sm }}>{"Carte interactive disponible sur l'app mobile"}</Txt>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm }}>
        {artisans.map((a) => (
          <Pressable key={a.artisan_id} testID={`map-artisan-${a.artisan_id}`} onPress={() => onSelect(a.artisan_id)} style={styles.pin}>
            <Ionicons name="location" size={20} color={colors.brand} />
            <View style={{ flex: 1, marginLeft: spacing.sm }}>
              <Txt weight="semibold" size="base">{a.name}</Txt>
              <Txt size="sm" color={colors.muted}>{a.trade_name}{a.city ? ` · ${a.city}` : ""}{a.distance_km != null ? ` · ${a.distance_km} km` : ""}</Txt>
            </View>
            <Txt weight="bold">{a.hourly_rate}€/h</Txt>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, overflow: "hidden" },
  banner: { flexDirection: "row", alignItems: "center", justifyContent: "center", paddingVertical: spacing.md, backgroundColor: colors.surfaceTertiary },
  pin: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
});
