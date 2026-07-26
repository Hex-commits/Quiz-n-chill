"use client";

/**
 * Last-resort boundary for errors thrown in the root layout itself.
 *
 * It replaces the root layout when it renders, so it has to supply its own
 * <html> and <body>, and it must not depend on any provider from that layout --
 * hence the inline styles instead of Tailwind classes or shadcn components.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          fontFamily: "system-ui, sans-serif",
          display: "flex",
          minHeight: "100vh",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "1rem",
          padding: "2rem",
          textAlign: "center",
        }}
      >
        <h1 style={{ fontSize: "1.5rem", fontWeight: 600 }}>
          Something went wrong
        </h1>
        <p style={{ color: "#666", maxWidth: "32rem" }}>{error.message}</p>
        <button
          type="button"
          onClick={reset}
          style={{
            border: "1px solid #ccc",
            borderRadius: "0.5rem",
            padding: "0.5rem 1rem",
            cursor: "pointer",
          }}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
