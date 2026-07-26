/**
 * Auto light/dark theme, respects the OS.
 * Use via `const t = useTheme()`.
 */
import React, { createContext, useContext, useMemo } from "react";
import { useColorScheme } from "react-native";
import { light, dark, Theme } from "./tokens";

const ThemeCtx = createContext<Theme>(light);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const scheme = useColorScheme();
  const theme = useMemo(() => (scheme === "dark" ? dark : light), [scheme]);
  return <ThemeCtx.Provider value={theme}>{children}</ThemeCtx.Provider>;
}

export const useTheme = () => useContext(ThemeCtx);
