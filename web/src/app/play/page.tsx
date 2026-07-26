import type { Metadata } from "next";

import { JoinForm } from "./join-form";

export const metadata: Metadata = { title: "Play together" };

export default function PlayPage() {
  return (
    <div className="mx-auto max-w-md space-y-6">
      <div className="space-y-1">
        <h1 className="text-3xl font-bold tracking-tight">Play together</h1>
        <p className="text-muted-foreground">
          Open a lobby and share the code, or join one you were given.
        </p>
      </div>
      <JoinForm />
    </div>
  );
}
