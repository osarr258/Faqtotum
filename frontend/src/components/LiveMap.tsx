/**
 * LiveMap — Uber-style map with nearby artisans + user position + radius.
 * Native only. Web fallback provided in LiveMap.web.tsx.
 */
import React from "react";
import { StyleSheet, View } from "react-native";
import MapView, { Marker, Circle, PROVIDER_DEFAULT } from "react-native-maps";
import { Ionicons } from "@expo/vector-icons";
import { Txt } from "@/src/components/ui";

type Artisan = {
  artisan_id: string;
  name: string;
  current_lat: number;
  current_lng: number;
  trade_name: string;
  eta_min: number;
  rating: number;
  available_now?: boolean;
};

const COLORS = { accent: "#C8A96B", bg: "#0B0B0B", white: "#FFFFFF" };

export default function LiveMap({
  center,
  radius,
  artisans,
  onSelect,
  selectedId,
}: {
  center: { lat: number; lng: number };
  radius: number; // km
  artisans: Artisan[];
  onSelect?: (a: Artisan) => void;
  selectedId?: string | null;
}) {
  const dLat = Math.max(0.02, radius / 55);
  const dLng = Math.max(0.02, radius / 40);
  return (
    <MapView
      testID="live-map"
      provider={PROVIDER_DEFAULT}
      style={StyleSheet.absoluteFill}
      region={{
        latitude: center.lat,
        longitude: center.lng,
        latitudeDelta: dLat,
        longitudeDelta: dLng,
      }}
    >
      {/* Radius */}
      <Circle
        center={{ latitude: center.lat, longitude: center.lng }}
        radius={radius * 1000}
        strokeColor="rgba(200,169,107,0.5)"
        fillColor="rgba(200,169,107,0.08)"
        strokeWidth={2}
      />
      {/* Client (you) */}
      <Marker coordinate={{ latitude: center.lat, longitude: center.lng }}>
        <View style={styles.mePin}>
          <View style={styles.mePinInner} />
        </View>
      </Marker>
      {/* Artisans */}
      {artisans.map((a) => (
        <Marker
          key={a.artisan_id}
          coordinate={{ latitude: a.current_lat, longitude: a.current_lng }}
          onPress={() => onSelect?.(a)}
          testID={`pin-${a.artisan_id}`}
        >
          <View style={[styles.pin, selectedId === a.artisan_id && styles.pinSelected]}>
            <Ionicons name="construct" size={14} color={COLORS.bg} />
            {a.available_now && <View style={styles.dotLive} />}
          </View>
          <View style={styles.pinLabel}>
            <Txt size="sm" weight="bold" style={{ color: COLORS.white, fontSize: 10 }}>
              {a.eta_min}min
            </Txt>
          </View>
        </Marker>
      ))}
    </MapView>
  );
}

const styles = StyleSheet.create({
  mePin: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: "rgba(59,130,246,0.25)",
    alignItems: "center",
    justifyContent: "center",
  },
  mePinInner: {
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: "#3B82F6",
    borderWidth: 2,
    borderColor: "#FFF",
  },
  pin: {
    width: 34, height: 34, borderRadius: 17,
    backgroundColor: COLORS.accent,
    alignItems: "center", justifyContent: "center",
    borderWidth: 2, borderColor: "#FFF",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 8,
    elevation: 6,
  },
  pinSelected: {
    transform: [{ scale: 1.2 }],
    borderColor: COLORS.accent,
    backgroundColor: "#FFF",
  },
  dotLive: {
    position: "absolute",
    top: -2, right: -2,
    width: 10, height: 10, borderRadius: 5,
    backgroundColor: "#34D399",
    borderWidth: 2, borderColor: "#FFF",
  },
  pinLabel: {
    marginTop: 2,
    backgroundColor: "rgba(11,11,11,0.85)",
    paddingHorizontal: 6, paddingVertical: 2,
    borderRadius: 6,
    alignSelf: "center",
  },
});
