import { ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { Difficulty, Source } from "@/lib/types";
import { cn } from "@/lib/utils";

const DIFFICULTY_LABEL: Record<Difficulty, string> = {
  easy: "Easy",
  medium: "Medium",
  hard: "Hard",
};

export function DifficultyBadge({
  difficulty,
  className,
}: {
  difficulty: Difficulty;
  className?: string;
}) {
  return (
    <Badge
      variant={difficulty === "hard" ? "destructive" : "secondary"}
      className={cn("shrink-0", className)}
    >
      {DIFFICULTY_LABEL[difficulty]}
    </Badge>
  );
}

/**
 * Link to the material a question was written from, so a player can check the
 * answers against it.
 *
 * Only rendered where the API actually sends a source — that is, after the
 * question has been answered. `rel="noreferrer"` because these are outbound
 * links to pages we do not control.
 */
export function SourceLink({
  source,
  className,
}: {
  source: Source | null;
  className?: string;
}) {
  if (!source) return null;

  return (
    <a
      href={source.url}
      target="_blank"
      rel="noreferrer"
      className={cn(
        "text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 text-sm underline underline-offset-4",
        className,
      )}
    >
      <ExternalLink className="size-3.5 shrink-0" aria-hidden />
      Source: {source.title ?? new URL(source.url).hostname}
    </a>
  );
}
