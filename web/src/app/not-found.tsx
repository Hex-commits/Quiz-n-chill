import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-md space-y-4 py-16 text-center">
      <h1 className="text-3xl font-bold tracking-tight">Not found</h1>
      <p className="text-muted-foreground">
        That quiz does not exist, or it has not been published yet.
      </p>
      <Button asChild>
        <Link href="/play">Play together</Link>
      </Button>
    </div>
  );
}
