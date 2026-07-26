import type { Metadata } from "next";

import { ApiErrorNotice } from "@/components/api-error-notice";
import { listQuizzes } from "@/lib/api";
import type { QuizSummary } from "@/lib/types";

import { LobbyRoom } from "./lobby-room";

type PageProps = { params: Promise<{ code: string }> };

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const { code } = await params;
  return { title: `Lobby ${code.toUpperCase()}` };
}

export default async function LobbyPage({ params }: PageProps) {
  const { code } = await params;

  // Fetched here so the host's topic picker is populated on first paint. The
  // live lobby state itself is polled client-side.
  let topics: QuizSummary[] = [];
  try {
    topics = await listQuizzes();
  } catch (cause) {
    return (
      <ApiErrorNotice
        message={cause instanceof Error ? cause.message : "Unknown error"}
      />
    );
  }

  return <LobbyRoom code={code.toUpperCase()} topics={topics} />;
}
