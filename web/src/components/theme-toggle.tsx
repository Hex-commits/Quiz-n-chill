"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";

/**
 * Both icons are always rendered and swapped with the `dark:` variant, so the
 * server and client markup are identical. The usual alternative -- tracking a
 * `mounted` flag in an effect -- causes a flash on load and trips the React
 * Compiler's set-state-in-effect rule.
 *
 * `resolvedTheme` is only read inside the click handler, which never runs
 * during SSR, so it cannot cause a hydration mismatch.
 */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
      aria-label="Toggle light and dark theme"
    >
      <Sun className="size-4 rotate-0 scale-0 transition-transform dark:scale-100" />
      <Moon className="absolute size-4 scale-100 transition-transform dark:scale-0" />
    </Button>
  );
}
