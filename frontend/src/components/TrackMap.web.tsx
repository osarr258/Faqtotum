import { StyleSheet, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import { Txt } from "@/src/components/ui";
import { colors, spacing } from "@/src/theme";

type Pt = { lat: number; lng: number };

// react-native-maps has no web support; render a stylized fallback.
export default function TrackMap({ artisan, client }: { artisan: Pt; client: Pt; status?: string }) {
  return (
    <LinearGradient colors={["#16161D", "#0B0B0F"]} style={StyleSheet.absoluteFill}>
      <View style={styles.center}>
        <View style={styles.row}>
          <Ionicons name="car-sport" size={28} color={colors.brand} />
          <View style={styles.dashes}>
            {[0, 1, 2, 3, 4].map((i) => <View key={i} style={styles.dash} />)}
          </View>
          <Ionicons name="home" size={26} color={colors.textInverse} />
        </View>
        <Txt size="sm" color={colors.muted} style={{ marginTop: spacing.md }}>Carte temps réel disponible sur l&apos;app mobile</Txt>
      </View>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  row: { flexDirection: "row", alignItems: "center" },
  dashes: { flexDirection: "row", marginHorizontal: spacing.md, gap: 6 },
  dash: { width: 14, height: 3, borderRadius: 2, backgroundColor: colors.brand },
});
