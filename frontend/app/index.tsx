import { useEffect } from "react";
import { View, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useAuth } from "@/src/context/AuthContext";
import { colors } from "@/src/theme";

export default function Index() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/welcome");
    } else if (user.role === "artisan") {
      router.replace("/(artisan)");
    } else {
      router.replace("/(client)");
    }
  }, [user, loading]);

  return (
    <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface }}>
      <ActivityIndicator color={colors.brand} size="large" />
    </View>
  );
}
