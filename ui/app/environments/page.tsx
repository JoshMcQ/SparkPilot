import Link from "next/link";
import { fetchEnvironmentsServer } from "@/lib/api-server";
import EnvironmentCreateForm from "./environment-create-form";

function badgeClass(status: string): string {
  return `badge ${status}`;
}

export default async function EnvironmentsPage() {
  const environments = await fetchEnvironmentsServer().catch(() => []);

  return (
    <section className="stack">
      <EnvironmentCreateForm />
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
              <th>Detail</th>
              <th>Tenant</th>
              <th>Mode</th>
              <th>Region</th>
              <th>Cluster ARN</th>
              <th>Namespace</th>
              <th>Virtual Cluster</th>
              <th>Customer Role</th>
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
                <td>
                  <Link className="inline-link" href={`/environments/${env.id}`}>
                    Open
                  </Link>
                </td>
                <td>{env.tenant_id}</td>
                <td>
                  <span className={badgeClass(env.provisioning_mode)}>{env.provisioning_mode}</span>
                </td>
                <td>{env.region}</td>
                <td>{env.eks_cluster_arn ?? "-"}</td>
                <td>{env.eks_namespace ?? "-"}</td>
                <td>{env.emr_virtual_cluster_id ?? "-"}</td>
                <td>{env.customer_role_arn}</td>
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
                <td colSpan={13} className="subtle">
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
