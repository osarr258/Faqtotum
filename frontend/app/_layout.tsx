import { Stack, useRouter } from "expo-router";
import { StatusBar } from "expo-status-bar";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { LogBox } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { KeyboardProvider } from "react-native-keyboard-controller";
import { useFonts } from "expo-font";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { AuthProvider, useAuth } from "@/src/context/AuthContext";
import LockScreen from "@/src/components/LockScreen";

LogBox.ignoreAllLogs(true);
SplashScreen.preventAutoHideAsync();

function GateContent() {
  const { locked } = useAuth();
  const router = useRouter();
  if (locked) {
    return <LockScreen onFallbackLogin={() => router.replace("/welcome")} />;
  }
  return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: "#0B0B0F" } }} />;
}

export default function RootLayout() {
  const [iconsLoaded, iconErr] = useIconFonts();
  const [fontsLoaded, fontErr] = useFonts({
    Jakarta400: require("@/assets/fonts/PlusJakartaSans_400Regular.ttf"),
    Jakarta500: require("@/assets/fonts/PlusJakartaSans_500Medium.ttf"),
    Jakarta600: require("@/assets/fonts/PlusJakartaSans_600SemiBold.ttf"),
    Jakarta700: require("@/assets/fonts/PlusJakartaSans_700Bold.ttf"),
    Jakarta800: require("@/assets/fonts/PlusJakartaSans_800ExtraBold.ttf"),
  });

  const ready = (iconsLoaded || iconErr) && (fontsLoaded || fontErr);

  useEffect(() => {
    if (ready) SplashScreen.hideAsync();
  }, [ready]);

  if (!ready) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <KeyboardProvider>
        <SafeAreaProvider>
          <AuthProvider>
            <StatusBar style="light" />
            <GateContent />
          </AuthProvider>
        </SafeAreaProvider>
      </KeyboardProvider>
    </GestureHandlerRootView>
  );
}
