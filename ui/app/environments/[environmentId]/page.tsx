import Link from "next/link";
import { type PreflightCheck } from "@/lib/api";
import { fetchEnvironmentPreflightServer, fetchEnvironmentServer } from "@/lib/api-server";

type EnvironmentDetailPageProps = {
  params: Promise<{ environmentId: string }>;
};

function badgeClass(status: string): string {
  return `badge ${status}`;
}

function asText(value: string | null | undefined, empty: string): string {
  if (!value) {
    return empty;
  }
  return value;
}

function preflightCounts(checks: PreflightCheck[]): { pass: number; warning: number; fail: number } {
  return checks.reduce(
    (acc, check) => {
      if (check.status === "pass") {
        acc.pass += 1;
      } else if (check.status === "warning") {
        acc.warning += 1;
      } else if (check.status === "fail") {
        acc.fail += 1;
      }
      return acc;
    },
    { pass: 0, warning: 0, fail: 0 }
  );
}

export default async function EnvironmentDetailPage({ params }: EnvironmentDetailPageProps) {
  const { environmentId } = await params;
  const environment = await fetchEnvironmentServer(environmentId);
  const preflight = await fetchEnvironmentPreflightServer(environmentId).catch(() => null);
  const preflightCheck = preflight?.checks.find((check) => check.code === "config.execution_role");
  const executionRoleValue = preflightCheck?.details?.execution_role_arn;
  const executionRoleArn = typeof executionRoleValue === "string" ? executionRoleValue : "";
  const counts = preflight ? preflightCounts(preflight.checks) : { pass: 0, warning: 0, fail: 0 };

  return (
    <section className="stack">
      <div className="card">
        <div className="card-header-row">
          <h3>Environment Detail</h3>
          <Link className="inline-link" href="/environments">
            Back to list
          </Link>
        </div>
        <div className="subtle">
          ID: {environment.id} | tenant: {environment.tenant_id}
        </div>
      </div>

      <div className="card">
        <h3>Mode + Status</h3>
        <div className="kv-grid">
          <div>
            <div className="subtle">Mode</div>
            <span className={badgeClass(environment.provisioning_mode)}>{environment.provisioning_mode}</span>
          </div>
          <div>
            <div className="subtle">Status</div>
            <span className={badgeClass(environment.status)}>{environment.status}</span>
          </div>
          <div>
            <div className="subtle">Region</div>
            <div>{environment.region}</div>
          </div>
          <div>
            <div className="subtle">Warm Pool</div>
            <div>{environment.warm_pool_enabled ? "enabled" : "disabled"}</div>
          </div>
          <div>
            <div className="subtle">Concurrency</div>
            <div>{environment.max_concurrent_runs}</div>
          </div>
          <div>
            <div className="subtle">vCPU Quota</div>
            <div>{environment.max_vcpu}</div>
          </div>
        </div>
      </div>

      {environment.provisioning_mode === "byoc_lite" ? (
        <div className="card">
          <h3>BYOC-Lite Runtime</h3>
          <div className="kv-grid">
            <div>
              <div className="subtle">EKS Cluster ARN</div>
              <div>{asText(environment.eks_cluster_arn, "Cluster ARN unavailable.")}</div>
            </div>
            <div>
              <div className="subtle">Namespace</div>
              <div>{asText(environment.eks_namespace, "Namespace unavailable.")}</div>
            </div>
            <div>
              <div className="subtle">EMR Virtual Cluster</div>
              <div>{asText(environment.emr_virtual_cluster_id, "Virtual cluster not created yet.")}</div>
            </div>
            <div>
              <div className="subtle">Customer Role ARN</div>
              <div>{environment.customer_role_arn}</div>
            </div>
            <div>
              <div className="subtle">Execution Role ARN</div>
              <div>{asText(executionRoleArn, "Execution role detail unavailable. Run preflight to refresh.")}</div>
            </div>
          </div>
        </div>
      ) : (
        <div className="card">
          <h3>Full BYOC Provisioning</h3>
          <div className="kv-grid">
            <div>
              <div className="subtle">Provisioning status</div>
              <div>{environment.status}</div>
            </div>
            <div>
              <div className="subtle">EKS Cluster ARN</div>
              <div>{asText(environment.eks_cluster_arn, "No cluster ARN in payload yet.")}</div>
            </div>
            <div>
              <div className="subtle">EMR Virtual Cluster</div>
              <div>{asText(environment.emr_virtual_cluster_id, "No virtual cluster id in payload yet.")}</div>
            </div>
          </div>
          <div className="subtle">
            Full-BYOC infra outputs are shown when available in the API payload. Missing values are expected during early provisioning.
          </div>
        </div>
      )}

      <div className="card">
        <h3>Preflight Snapshot</h3>
        {preflight ? (
          <>
            <div className="subtle">
              ready={preflight.ready ? "true" : "false"} | pass={counts.pass} | warning={counts.warning} | fail={counts.fail}
            </div>
            <ul className="preflight-list">
              {preflight.checks.map((check) => (
                <li key={`${check.code}-${check.status}`}>
                  [{check.status}] {check.code}: {check.message}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <div className="subtle">
            Preflight details are unavailable from the API right now.
          </div>
        )}
      </div>
    </section>
  );
}
