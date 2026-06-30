import { View, StyleSheet } from "react-native";
import MapView, { Marker, PROVIDER_DEFAULT } from "react-native-maps";
import { colors, radius } from "@/src/theme";

type Artisan = { artisan_id: string; name: string; trade_name: string; hourly_rate: number; lat?: number | null; lng?: number | null };

export default function ArtisanMap({ artisans, userLocation, onSelect }: {
  artisans: Artisan[];
  userLocation?: { lat: number; lng: number } | null;
  onSelect: (id: string) => void;
}) {
  const withCoords = artisans.filter((a) => a.lat != null && a.lng != null);
  const initial = userLocation
    ? { latitude: userLocation.lat, longitude: userLocation.lng }
    : withCoords[0]
    ? { latitude: withCoords[0].lat as number, longitude: withCoords[0].lng as number }
    : { latitude: 46.6, longitude: 2.4 };

  return (
    <View style={styles.container}>
      <MapView
        testID="artisan-map"
        provider={PROVIDER_DEFAULT}
        style={StyleSheet.absoluteFill}
        initialRegion={{ latitude: initial.latitude, longitude: initial.longitude, latitudeDelta: userLocation ? 0.4 : 8, longitudeDelta: userLocation ? 0.4 : 8 }}
        showsUserLocation={!!userLocation}
      >
        {withCoords.map((a) => (
          <Marker
            key={a.artisan_id}
            coordinate={{ latitude: a.lat as number, longitude: a.lng as number }}
            title={a.name}
            description={`${a.trade_name} · ${a.hourly_rate}€/h`}
            onCalloutPress={() => onSelect(a.artisan_id)}
          />
        ))}
      </MapView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, borderRadius: radius.md, overflow: "hidden", backgroundColor: colors.surfaceSecondary },
});
