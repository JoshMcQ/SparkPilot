import Link from "next/link";
import { fetchEnvironments, fetchRuns } from "@/lib/api";

export default async function HomePage() {
  let environments = 0;
  let runs = 0;
  let running = 0;
  try {
    const [envData, runData] = await Promise.all([fetchEnvironments(), fetchRuns()]);
    environments = envData.length;
    runs = runData.length;
    running = runData.filter((r) => ["accepted", "running", "dispatching"].includes(r.state)).length;
  } catch {
    // Keep UI operational if API is unavailable.
  }

  return (
    <section className="stack">
      <div className="card-grid">
        <article className="card">
          <h3>Environments</h3>
          <div>{environments}</div>
          <div className="subtle">Dedicated tenant clusters</div>
        </article>
        <article className="card">
          <h3>Total Runs</h3>
          <div>{runs}</div>
          <div className="subtle">Submitted job runs</div>
        </article>
        <article className="card">
          <h3>In Flight</h3>
          <div>{running}</div>
          <div className="subtle">Dispatching/accepted/running</div>
        </article>
      </div>

      <div className="card-grid">
        <article className="card">
          <h3>Environment Operations</h3>
          <p className="subtle">Provisioning state and isolation profile per tenant.</p>
          <Link href="/environments">Open environments</Link>
        </article>
        <article className="card">
          <h3>Run Operations</h3>
          <p className="subtle">Run status, EMR IDs, and deterministic log pointers.</p>
          <Link href="/runs">Open runs</Link>
        </article>
      </div>
    </section>
  );
}

