import { StyleSheet } from "react-native";
import MapView, { Marker, PROVIDER_DEFAULT } from "react-native-maps";
import { colors } from "@/src/theme";

type Pt = { lat: number; lng: number };

export default function TrackMap({ artisan, client }: { artisan: Pt; client: Pt; status?: string }) {
  const midLat = (artisan.lat + client.lat) / 2;
  const midLng = (artisan.lng + client.lng) / 2;
  const dLat = Math.max(0.02, Math.abs(artisan.lat - client.lat) * 2.2);
  const dLng = Math.max(0.02, Math.abs(artisan.lng - client.lng) * 2.2);
  return (
    <MapView
      testID="track-map"
      provider={PROVIDER_DEFAULT}
      style={StyleSheet.absoluteFill}
      region={{ latitude: midLat, longitude: midLng, latitudeDelta: dLat, longitudeDelta: dLng }}
    >
      <Marker coordinate={{ latitude: client.lat, longitude: client.lng }} title="Vous" pinColor={colors.brand} />
      <Marker coordinate={{ latitude: artisan.lat, longitude: artisan.lng }} title="Artisan" />
    </MapView>
  );
}
