import { fetchEnvironments } from "@/lib/api";

function badgeClass(status: string): string {
  return `badge ${status}`;
}

export default async function EnvironmentsPage() {
  const environments = await fetchEnvironments().catch(() => []);

  return (
    <section className="stack">
      <div className="card">
        <h3>Tenant Environments</h3>
        <div className="subtle">
          Environment mode determines ownership boundaries: full mode provisions runtime infra, BYOC-Lite uses your existing
          EKS cluster namespace.
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Environment</th>
              <th>Tenant</th>
              <th>Mode</th>
              <th>Region</th>
              <th>Namespace</th>
              <th>Status</th>
              <th>Warm Pool</th>
              <th>Concurrency</th>
              <th>vCPU Quota</th>
            </tr>
          </thead>
          <tbody>
            {environments.map((env) => (
              <tr key={env.id}>
                <td>{env.id}</td>
                <td>{env.tenant_id}</td>
                <td>{env.provisioning_mode}</td>
                <td>{env.region}</td>
                <td>{env.eks_namespace ?? "-"}</td>
                <td>
                  <span className={badgeClass(env.status)}>{env.status}</span>
                </td>
                <td>{env.warm_pool_enabled ? "enabled" : "disabled"}</td>
                <td>{env.max_concurrent_runs}</td>
                <td>{env.max_vcpu}</td>
              </tr>
            ))}
            {environments.length === 0 ? (
              <tr>
                <td colSpan={9} className="subtle">
                  No environments available.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
