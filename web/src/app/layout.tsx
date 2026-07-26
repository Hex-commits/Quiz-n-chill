import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { SiteHeader } from "@/components/site-header";
import { ThemeProvider } from "@/components/theme-provider";
import { Toaster } from "@/components/ui/sonner";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Quiz Quiz",
    template: "%s · Quiz Quiz",
  },
  description: "A quiz app with a Next.js frontend and a Python backend.",
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
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
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
            Next.js renders · FastAPI decides · Supabase stores
          </footer>
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
