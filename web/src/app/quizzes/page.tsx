import type { Metadata } from "next";

import { ApiErrorNotice } from "@/components/api-error-notice";
import { QuizCard } from "@/components/quiz-card";
import { listQuizzes } from "@/lib/api";
import type { QuizSummary } from "@/lib/types";

export const metadata: Metadata = { title: "Quizzes" };

// Rendered on every request so a newly published quiz shows up immediately.
export const dynamic = "force-dynamic";

export default async function QuizzesPage() {
  let quizzes: QuizSummary[] = [];
  let error: string | null = null;

  try {
    quizzes = await listQuizzes();
  } catch (cause) {
    error = cause instanceof Error ? cause.message : "Unknown error";
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-3xl font-bold tracking-tight">Topics</h1>
        <p className="text-muted-foreground">
          Assign each answer to a category — and spot the ones that belong
          nowhere.
        </p>
      </div>

      {error ? <ApiErrorNotice message={error} /> : null}

      {!error && quizzes.length === 0 ? (
        <p className="text-muted-foreground rounded-lg border border-dashed p-8 text-center text-sm">
          No topics yet. Run <code>npm run db:reset</code> to load the seed
          data.
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {quizzes.map((quiz) => (
          <QuizCard key={quiz.id} quiz={quiz} />
        ))}
      </div>
    </div>
  );
}
