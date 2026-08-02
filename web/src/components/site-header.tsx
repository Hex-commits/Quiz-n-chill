import Link from "next/link";

import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";

export function SiteHeader() {
  return (
    <header className="border-b bg-background/80 sticky top-0 z-40 backdrop-blur">
      <div className="mx-auto flex h-(--header-h) w-full max-w-5xl items-center gap-6 px-4">
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
