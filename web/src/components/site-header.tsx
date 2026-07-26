import Link from "next/link";
import { BrainCircuit } from "lucide-react";

import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";

const links = [
  { href: "/quizzes", label: "Topics" },
  { href: "/play", label: "Play together" },
];

export function SiteHeader() {
  return (
    <header className="border-b bg-background/80 sticky top-0 z-40 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-5xl items-center gap-6 px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <BrainCircuit className="size-5" aria-hidden />
          <span>Quiz Quiz</span>
        </Link>

        <nav className="flex items-center gap-1">
          {links.map((link) => (
            <Button key={link.href} variant="ghost" size="sm" asChild>
              <Link href={link.href}>{link.label}</Link>
            </Button>
          ))}
        </nav>

        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
