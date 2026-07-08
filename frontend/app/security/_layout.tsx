import { Stack } from "expo-router";

export default function SecurityLayout() {
  return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: "#0B0B0F" } }} />;
}
