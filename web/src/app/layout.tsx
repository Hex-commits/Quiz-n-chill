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
      {/*
        `h-dvh` and `overflow-hidden`, not `min-h-full`. The page itself never
        scrolls -- the header and footer are fixed furniture and `main` below is
        the only thing that can move. That is what makes "no scrollbar" a
        property of the shell rather than something every page has to arrange
        for itself.

        `dvh` rather than `vh` because mobile browsers grow and shrink their
        chrome as you scroll, and `100vh` is the *tall* measurement -- using it
        puts the footer under the address bar on every phone.
      */}
      <body className="flex h-dvh flex-col overflow-hidden">
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
          {/*
            `min-h-0` is doing the load-bearing work: a flex child defaults to
            `min-height: auto`, which means it refuses to shrink below its
            content and pushes the footer off the bottom instead of scrolling.
            Without it the `overflow-y-auto` never engages.

            Wider than it was, and measured rather than picked. At `max-w-7xl`
            the board came out 960px on a 1920px screen -- 640px of the window
            unused -- which held it to four columns and ten cards to three rows.
            96rem gives six columns at 1920 and five at 1366, so the board is
            two rows on anything a game is played on.
          */}
          <main className="mx-auto min-h-0 w-full max-w-[96rem] flex-1 overflow-y-auto px-4 py-6">
            {children}
          </main>
          <footer className="text-muted-foreground shrink-0 border-t px-4 py-3 text-center text-xs">
            Hier könnte ihre Werbung stehen!
          </footer>
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
