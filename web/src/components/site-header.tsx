import Link from "next/link";

import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";

export function SiteHeader() {
  return (
    <header className="border-b bg-background/80 sticky top-0 z-40 backdrop-blur">
      {/*
        Logo left, theme toggle right, nothing between. The one nav link used to
        be "Play together" pointing at /play -- which is where `/` redirects
        anyway, and where the logo already goes, so it was a second button to
        the page you were almost certainly already on.
      */}
      <div className="mx-auto flex h-14 w-full max-w-5xl items-center gap-6 px-4">
        <Link href="/" className="text-base">
          <Logo />
        </Link>

        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
