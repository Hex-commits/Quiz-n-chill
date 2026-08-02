import type { Metadata } from "next";

import { ApiErrorNotice } from "@/components/api-error-notice";
import { listSubjects } from "@/lib/api";
import type { Subject } from "@/lib/types";

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

  let subjects: Subject[] = [];
  try {
    subjects = await listSubjects();
  } catch (cause) {
    return (
      <ApiErrorNotice
        message={cause instanceof Error ? cause.message : "Unknown error"}
      />
    );
  }

  return <LobbyRoom code={code.toUpperCase()} subjects={subjects} />;
}
