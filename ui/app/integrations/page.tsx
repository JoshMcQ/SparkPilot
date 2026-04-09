import Link from "next/link";

const AIRFLOW_DAG_SNIPPET = `with DAG(dag_id="sparkpilot_runs") as dag:
    submit = SparkPilotSubmitRunOperator(
        task_id="submit",
        sparkpilot_conn_id="sparkpilot_default",
        job_id="<job-id>",
        wait_for_completion=False,
    )

    wait_terminal = SparkPilotRunSensor(
        task_id="wait_terminal",
        sparkpilot_conn_id="sparkpilot_default",
        run_id=submit.output["id"],
    )`;

const DAGSTER_SNIPPET = `@job(resource_defs={"sparkpilot": sparkpilot_resource})
def sparkpilot_submit_wait_job():
    sparkpilot_wait_for_run_op(sparkpilot_submit_run_op())`;

export default function IntegrationsPage() {
  return (
    <section className="stack">
      <div className="card">
        <div className="eyebrow">WORKFLOW INTEGRATIONS</div>
        <h3>SparkPilot integration surfaces</h3>
        <p className="subtle" style={{ marginTop: 8 }}>
          The web app, API, and CLI are the primary validated workflow surfaces today.
          Airflow and Dagster packages exist in-source and are still in limited live validation.
        </p>
      </div>

      <div className="card-grid">
        <article className="card">
          <h3>Airflow Provider</h3>
          <p className="subtle">Hook/operator/sensor/trigger package exists. Production scheduler validation depth is still limited.</p>
          <div className="button-row">
            <a
              href="https://github.com/JoshMcQ/SparkPilot/tree/main/providers/airflow"
              target="_blank"
              rel="noopener noreferrer"
              className="button button-secondary"
            >
              Open provider source
            </a>
          </div>
          <pre className="logs" style={{ marginTop: 10 }}>{AIRFLOW_DAG_SNIPPET}</pre>
        </article>

        <article className="card">
          <h3>Dagster Package</h3>
          <p className="subtle">Resource + ops + assets package exists. End-to-end customer runtime validation is still limited.</p>
          <div className="button-row">
            <a
              href="https://github.com/JoshMcQ/SparkPilot/tree/main/providers/dagster"
              target="_blank"
              rel="noopener noreferrer"
              className="button button-secondary"
            >
              Open package source
            </a>
          </div>
          <pre className="logs" style={{ marginTop: 10 }}>{DAGSTER_SNIPPET}</pre>
        </article>
      </div>

      <div className="card">
        <h3>Current workflow fit</h3>
        <ol className="guided-steps">
          <li>Platform admin configures identity/team scope and validates onboarding gates.</li>
          <li>Teams submit batch runs through UI, API, or CLI.</li>
          <li>SparkPilot preflight gates and dispatches runs; Runs UI surfaces state, logs, and diagnostics.</li>
          <li>Usage and KPI views provide operational evidence while broader cost reconciliation remains environment-dependent.</li>
        </ol>
        <p className="subtle" style={{ marginTop: 10 }}>
          Coming soon for customer rollout claims: interactive endpoints, customer-facing template/security workflows,
          and full multi-engine orchestration guarantees.
        </p>
        <div className="button-row" style={{ marginTop: 12 }}>
          <Link href="/access" className="button button-secondary">Access</Link>
          <Link href="/policies" className="button button-secondary">Policies</Link>
          <Link href="/runs" className="button button-secondary">Runs</Link>
          <Link href="/costs" className="button button-secondary">Costs</Link>
        </div>
      </div>
    </section>
  );
}

