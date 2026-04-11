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
        <h3>SparkPilot in enterprise workflow operations</h3>
        <p className="subtle" style={{ marginTop: 8 }}>
          This is the in-product integration surface for orchestrator-led operations. Teams submit through Airflow or
          Dagster, SparkPilot enforces preflight and governance, and operators monitor runs, diagnostics, and costs.
        </p>
      </div>

      <div className="card-grid">
        <article className="card">
          <h3>Airflow Provider</h3>
          <p className="subtle">First-class hook/operator/sensor/trigger provider with deferrable waiting support.</p>
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
          <p className="subtle">Resource + ops + assets for submit/wait/cancel lifecycle with OIDC-authenticated API calls.</p>
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
        <h3>Operational Workflow Fit</h3>
        <ol className="guided-steps">
          <li>Platform admin configures identity/team/scope and budget guardrails in Access + Policies.</li>
          <li>Workflow orchestrator submits SparkPilot runs from Airflow DAGs or Dagster jobs/assets.</li>
          <li>SparkPilot preflight gates and dispatches; Runs UI is used for state, logs, and diagnostics.</li>
          <li>Costs UI reconciles team showback from estimated and CUR-backed actual usage.</li>
        </ol>
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

