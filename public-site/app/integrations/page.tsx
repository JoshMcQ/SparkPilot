import { appHref } from "@/lib/app-url";

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
          The web app, API, and CLI are the primary operating surfaces today.
          Airflow and Dagster packages are available in-source for team evaluation and rollout planning.
        </p>
      </div>

      <div className="card-grid">
        <article className="card">
          <h3>Airflow Provider</h3>
          <p className="subtle">Hook/operator/sensor/trigger package for integrating SparkPilot run operations into Airflow DAGs.</p>
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
          <p className="subtle">Resource + ops + assets package for Dagster-first teams standardizing run submission and monitoring.</p>
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
          Planned next: interactive endpoint operations, richer template/security workflows, and broader multi-engine rollout.
        </p>
        <div className="button-row" style={{ marginTop: 12 }}>
          <a href={appHref("/access")} className="button button-secondary">Access</a>
          <a href={appHref("/policies")} className="button button-secondary">Policies</a>
          <a href={appHref("/runs")} className="button button-secondary">Runs</a>
          <a href={appHref("/costs")} className="button button-secondary">Costs</a>
        </div>
      </div>
    </section>
  );
}
