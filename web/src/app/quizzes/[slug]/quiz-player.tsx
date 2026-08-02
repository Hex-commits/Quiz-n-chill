"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Check, Loader2, RotateCcw, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { DifficultyBadge, SourceLink } from "@/components/source-link";
import { checkAssignment } from "@/lib/api";
import { shuffleBySeed } from "@/lib/shuffle";
import type { CheckResult, Item, QuizDetail } from "@/lib/types";
import { cn } from "@/lib/utils";



/**
 * Interaction only. Which item belongs to which category is decided entirely by
 * the Python API -- this component collects placements and renders the verdict
 * it gets back from /check.
 *
 * Click an item to pick it up, then click a category to drop it there. Plain
 * clicks rather than drag-and-drop: no extra dependency, and it works on touch
 * and with a keyboard for free.
 */
export function QuizPlayer({ quiz }: { quiz: QuizDetail }) {
  const [placements, setPlacements] = useState<Record<string, string>>({});
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [result, setResult] = useState<CheckResult | null>(null);
  const [busy, setBusy] = useState(false);

  const itemsById = useMemo(
    () => new Map(quiz.items.map((item) => [item.id, item])),
    [quiz.items],
  );

  const categories = useMemo(
    () => shuffleBySeed(quiz.categories, quiz.id, (category) => category.id),
    [quiz.categories, quiz.id],
  );

  const unplaced = quiz.items.filter((item) => !(item.id in placements));
  const allPlaced = unplaced.length === 0;

  function place(target: string) {
    if (!selectedItemId) return;
    setPlacements((current) => ({ ...current, [selectedItemId]: target }));
    setSelectedItemId(null);
  }

  function unplace(itemId: string) {
    setPlacements((current) => {
      const next = { ...current };
      delete next[itemId];
      return next;
    });
  }

  function reset() {
    setPlacements({});
    setSelectedItemId(null);
    setResult(null);
  }

  async function submit() {
    setBusy(true);
    try {
      const assignments = quiz.items.map((item) => {
        const target = placements[item.id];
        return {
          item_id: item.id,
          category_id: target ?? null,
        };
      });
      setResult(await checkAssignment(quiz.slug, assignments));
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not check.");
    } finally {
      setBusy(false);
    }
  }

  function itemsIn(target: string): Item[] {
    return Object.entries(placements)
      .filter(([, value]) => value === target)
      .map(([itemId]) => itemsById.get(itemId))
      .filter((item): item is Item => item !== undefined);
  }

  if (result) {
    const percent = Math.round((result.score / result.max_score) * 100);
    const labelFor = (categoryId: string | null) =>
      categoryId
        ? (quiz.categories.find((c) => c.id === categoryId)?.label ?? "?")
        : "nicht zugeordnet";

    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <Card>
          <CardHeader>
            <CardDescription>{quiz.title}</CardDescription>
            <CardTitle className="text-3xl">
              {result.score} / {result.max_score} correct
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Progress value={percent} />
            <p className="text-muted-foreground text-sm">{percent}%</p>
            <SourceLink source={result.source} className="pt-1" />
          </CardContent>
          <CardFooter className="gap-2">
            <Button onClick={reset}>
              <RotateCcw className="size-4" aria-hidden />
              Try again
            </Button>
            <Button variant="ghost" asChild>
              <Link href="/play">Play together</Link>
            </Button>
          </CardFooter>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Solution</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {result.results.map((entry) => (
              <div key={entry.item_id} className="border-b pb-2 text-sm last:border-0">
                <div className="flex items-start gap-3">
                  {entry.is_correct ? (
                    <Check
                      className="mt-0.5 size-4 shrink-0 text-success"
                      aria-label="Correct"
                    />
                  ) : (
                    <X
                      className="text-destructive mt-0.5 size-4 shrink-0"
                      aria-label="Incorrect"
                    />
                  )}
                  <span className="font-medium">{entry.label}</span>
                  <span className="text-muted-foreground ml-auto text-right">
                    {entry.is_correct ? (
                      labelFor(entry.correct_category_id)
                    ) : (
                      <>
                        <span className="line-through">
                          {labelFor(entry.assigned_category_id)}
                        </span>{" "}
                        → {labelFor(entry.correct_category_id)}
                      </>
                    )}
                  </span>
                </div>
                {entry.explanation ? (
                  <p className="text-muted-foreground mt-1 pl-7 text-xs">
                    {entry.explanation}
                  </p>
                ) : null}
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-bold tracking-tight">{quiz.title}</h1>
          <DifficultyBadge difficulty={quiz.difficulty} />
        </div>
        {quiz.description ? (
          <p className="text-muted-foreground">{quiz.description}</p>
        ) : null}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {selectedItemId
              ? `Now pick where "${itemsById.get(selectedItemId)?.label}" belongs`
              : "Pick an answer"}
          </CardTitle>
          <CardDescription>
            {unplaced.length} of {quiz.items.length} left. Every answer belongs
            to exactly one category.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {unplaced.map((item) => (
            <Button
              key={item.id}
              variant={selectedItemId === item.id ? "default" : "outline"}
              size="sm"
              onClick={() =>
                setSelectedItemId(selectedItemId === item.id ? null : item.id)
              }
              aria-pressed={selectedItemId === item.id}
            >
              {item.label}
            </Button>
          ))}
          {allPlaced ? (
            <p className="text-muted-foreground text-sm">
              Everything is placed. Check your answers below.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {categories.map((category) => (
          <DropTarget
            key={category.id}
            title={category.label}
            items={itemsIn(category.id)}
            armed={selectedItemId !== null}
            onPlace={() => place(category.id)}
            onRemove={unplace}
          />
        ))}
      </div>

      <div className="flex gap-2">
        <Button onClick={submit} disabled={busy || quiz.items.length === 0}>
          {busy ? <Loader2 className="size-4 animate-spin" /> : null}
          Check answers
        </Button>
        <Button
          variant="ghost"
          onClick={reset}
          disabled={busy || Object.keys(placements).length === 0}
        >
          Reset
        </Button>
      </div>
    </div>
  );
}

function DropTarget({
  title,
  description,
  icon,
  items,
  armed,
  onPlace,
  onRemove,
}: {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  items: Item[];
  armed: boolean;
  onPlace: () => void;
  onRemove: (itemId: string) => void;
}) {
  return (
    <Card
      className={cn(
        "transition-colors",
        armed && "border-primary cursor-pointer",
      )}
      onClick={armed ? onPlace : undefined}
    >
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {icon}
          {title}
        </CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="flex min-h-16 flex-wrap gap-2">
        {items.length === 0 ? (
          <p className="text-muted-foreground text-sm">Empty</p>
        ) : (
          items.map((item) => (
            <Badge
              key={item.id}
              variant="secondary"
              asChild
              className="cursor-pointer"
            >
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onRemove(item.id);
                }}
                aria-label={`Remove ${item.label}`}
              >
                {item.label}
                <X className="size-3" aria-hidden />
              </button>
            </Badge>
          ))
        )}
      </CardContent>
    </Card>
  );
}
