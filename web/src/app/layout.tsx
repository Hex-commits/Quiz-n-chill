import type { Metadata } from "next";
import { Geist_Mono, Outfit } from "next/font/google";

import { SiteHeader } from "@/components/site-header";
import { ThemeProvider } from "@/components/theme-provider";
import { Toaster } from "@/components/ui/sonner";

import "./globals.css";

/*
 * Outfit: a geometric sans with near-circular bowls and a tall x-height. It
 * reads as friendly and game-like where a neo-grotesque reads as software,
 * which is the right register for a party quiz.
 *
 * A variable font, so all weights from 400 to 900 arrive in one file -- the
 * heavy end matters here, because headings at 800 are a good part of what makes
 * this look like a game rather than a form.
 *
 * `next/font` downloads it at build time and serves it from our own origin, so
 * despite the name nothing is requested from Google at runtime. It also emits
 * the same `font-display: swap` and unicode-range subsetting by hand-written
 * `@font-face` rules would.
 *
 * OFL licensed. https://github.com/Outfitio/Outfit-Fonts
 */
const outfit = Outfit({
  variable: "--font-outfit",
  // latin-ext for the German set -- umlauts live in latin, but ligatures and
  // the odd borrowed name do not.
  subsets: ["latin", "latin-ext"],
});

// Kept for the lobby code and the scores, where digits have to line up.
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Quiz & Chill",
    template: "%s · Quiz & Chill",
  },
  description: "Ordne zu, was zusammengehört — allein oder zu mehreren.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // next-themes writes the theme class onto <html> before hydration, so the
    // server and client markup differ by design here.
    <html
      lang="en"
      suppressHydrationWarning
      className={`${outfit.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        {/*
          Dark is the default rather than following the OS. `enableSystem` is
          off so the app does not silently flip to light on a light-mode
          machine; the header toggle overrides this and persists the choice.
        */}
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem={false}
          disableTransitionOnChange
        >
          <SiteHeader />
          <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
            {children}
          </main>
          <footer className="text-muted-foreground border-t px-4 py-6 text-center text-xs">
            Hier könnte ihre Werbung stehen!
          </footer>
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
