"use client";
export default function GlobalError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="card" style={{padding: "2rem"}}>
      <h2>Something went wrong</h2>
      <p style={{color: "var(--text-muted)"}}>{error.message}</p>
      <button className="button" onClick={reset}>Try again</button>
    </div>
  );
}
