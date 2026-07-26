import Link from "next/link";
import { LayoutGrid, Tags } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { QuizSummary } from "@/lib/types";

export function QuizCard({ quiz }: { quiz: QuizSummary }) {
  return (
    <Card className="flex flex-col">
      <CardHeader>
        <CardTitle className="text-lg">{quiz.title}</CardTitle>
        {quiz.description ? (
          <CardDescription>{quiz.description}</CardDescription>
        ) : null}
      </CardHeader>

      <CardContent className="text-muted-foreground flex flex-1 items-center gap-4 text-sm">
        <span className="flex items-center gap-1.5">
          <Tags className="size-4" aria-hidden />
          {quiz.category_count} categories
        </span>
        <span className="flex items-center gap-1.5">
          <LayoutGrid className="size-4" aria-hidden />
          {quiz.item_count} answers
        </span>
      </CardContent>

      <CardFooter>
        <Button asChild className="w-full">
          <Link href={`/quizzes/${quiz.slug}`}>Play</Link>
        </Button>
      </CardFooter>
    </Card>
  );
}
