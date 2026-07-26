import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function HomePage() {
  return (
    <div className="flex flex-col items-center justify-center gap-8 py-24 text-center">
      <h1 className="text-4xl font-bold tracking-tight text-balance sm:text-5xl">
        Quiz Quiz
      </h1>
      <Button asChild size="lg">
        <Link href="/play">
          Play together
          <ArrowRight className="size-4" aria-hidden />
        </Link>
      </Button>
    </div>
  );
}
