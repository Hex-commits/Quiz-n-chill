import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ApiErrorNotice } from "@/components/api-error-notice";
import { ApiError, getQuiz } from "@/lib/api";
import type { QuizDetail } from "@/lib/types";

import { QuizPlayer } from "./quiz-player";

type PageProps = { params: Promise<{ slug: string }> };

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const { slug } = await params;
  try {
    const quiz = await getQuiz(slug);
    return { title: quiz.title, description: quiz.description ?? undefined };
  } catch {
    return { title: "Quiz" };
  }
}

export default async function QuizPage({ params }: PageProps) {
  const { slug } = await params;

  let quiz: QuizDetail;
  try {
    quiz = await getQuiz(slug);
  } catch (cause) {
    if (cause instanceof ApiError && cause.status === 404) {
      notFound();
    }
    return (
      <ApiErrorNotice
        message={cause instanceof Error ? cause.message : "Unknown error"}
      />
    );
  }

  return <QuizPlayer quiz={quiz} />;
}
