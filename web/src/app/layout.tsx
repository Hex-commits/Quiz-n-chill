import type { Metadata } from "next";
import { Geist_Mono, Outfit } from "next/font/google";

import { SiteHeader } from "@/components/site-header";
import { ThemeProvider } from "@/components/theme-provider";
import { Toaster } from "@/components/ui/sonner";

import "./globals.css";

const outfit = Outfit({
  variable: "--font-outfit",
  subsets: ["latin", "latin-ext"],
});

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
    <html
      lang="en"
      suppressHydrationWarning
      className={`${outfit.variable} ${geistMono.variable} h-full antialiased`}
    >
      {/*
        The shell is exactly the viewport, and never scrolls itself.

        A page-level scrollbar on a game board is a real cost: half the board
        below the fold means every player is scrolling to see the thing they are
        being asked about, and on a shared screen they are scrolling past each
        other. So the chrome is pinned and `main` is the one scrolling box —
        which means a page that fits shows no scrollbar at all, and a page that
        genuinely cannot fit (the answers at the end of a game, a phone in
        landscape) still scrolls, just without moving the header out of reach.

        `h-dvh` rather than `h-screen`: on mobile `100vh` is the viewport with
        the browser chrome *hidden*, so a shell sized to it is taller than what
        is actually on screen — the bottom is cut off until the address bar
        slides away.
      */}
      <body className="flex h-dvh flex-col overflow-hidden">
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem={false}
          disableTransitionOnChange
        >
          <SiteHeader />
          <main
            data-scroll-root
            /* No width cap here: a page in a scrolling box cannot break out of
               one, and the board wants the whole screen while everything else
               wants a reading measure. Each page states its own. */
            className="flex w-full min-h-0 flex-1 flex-col overflow-y-auto px-4 py-4 sm:py-6 lg:py-3"
          >
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
