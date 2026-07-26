import Link from "next/link";
import { ArrowRight, Database, Layers, Server } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const layers = [
  {
    icon: Layers,
    title: "Next.js frontend",
    description:
      "Renders and handles interaction only. It holds no rules about what a correct answer is.",
  },
  {
    icon: Server,
    title: "FastAPI backend",
    description:
      "Owns every rule: which item belongs where, which are fakes, how an assignment is scored.",
  },
  {
    icon: Database,
    title: "Supabase Postgres",
    description:
      "Stores topics, categories and answers — and nothing about who played or how they did.",
  },
];

export default function HomePage() {
  return (
    <div className="space-y-12">
      <section className="space-y-4 py-8">
        <h1 className="text-4xl font-bold tracking-tight text-balance sm:text-5xl">
          Zuordnungsfragen. Logic in Python.
        </h1>
        <p className="text-muted-foreground max-w-2xl text-lg text-pretty">
          Assign answers to categories and catch the fakes hidden among them. A
          development scaffold: typed API contract, dockerized services and a
          local Supabase stack that matches production.
        </p>
        <div className="flex flex-wrap gap-3 pt-2">
          <Button asChild size="lg">
            <Link href="/play">
              Play together
              <ArrowRight className="size-4" aria-hidden />
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/quizzes">Practise solo</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <a
              href={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001"}/docs`}
              target="_blank"
              rel="noreferrer"
            >
              API docs
            </a>
          </Button>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        {layers.map(({ icon: Icon, title, description }) => (
          <Card key={title}>
            <CardHeader>
              <Icon className="text-muted-foreground size-5" aria-hidden />
              <CardTitle className="text-base">{title}</CardTitle>
              <CardDescription>{description}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </section>

      <section>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Where the logic goes</CardTitle>
          </CardHeader>
          <CardContent className="text-muted-foreground space-y-2 text-sm">
            <p>
              Grading rules live in{" "}
              <code className="text-foreground">
                api/app/services/scoring.py
              </code>
              , isolated from the database and HTTP so they stay easy to test.
            </p>
            <p>
              An answer’s category <em>is</em> the solution, so the frontend
              never receives{" "}
              <code className="text-foreground">category_id</code> while
              playing. It arrives only in the response to{" "}
              <code className="text-foreground">/check</code>, which stores
              nothing.
            </p>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
