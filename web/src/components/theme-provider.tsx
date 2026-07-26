"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ComponentProps } from "react";

/**
 * shadcn's `Toaster` calls `useTheme()`, so next-themes has to be mounted above
 * it for toasts to follow the active theme. It also gives the whole app
 * light/dark switching -- the CSS variables shadcn generated are already
 * defined for both.
 */
export function ThemeProvider({
  children,
  ...props
}: ComponentProps<typeof NextThemesProvider>) {
  return <NextThemesProvider {...props}>{children}</NextThemesProvider>;
}
