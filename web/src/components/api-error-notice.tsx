import { AlertCircle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

/**
 * Shown when a server component cannot reach the Python API. During local
 * development that is nearly always a service that has not been started yet,
 * so the fix is spelled out rather than left as "something went wrong".
 */
export function ApiErrorNotice({ message }: { message: string }) {
  return (
    <Alert variant="destructive" className="mx-auto w-full max-w-5xl">
      <AlertCircle className="size-4" aria-hidden />
      <AlertTitle>Could not load data from the API</AlertTitle>
      <AlertDescription>
        <p>{message}</p>
        <p className="mt-2">
          Check that both are running: <code>npm run db:start</code> for
          Supabase, then <code>docker compose up</code> for the API and
          frontend.
        </p>
      </AlertDescription>
    </Alert>
  );
}
