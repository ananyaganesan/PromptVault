import { useCallback, useState, useSyncExternalStore } from "react";
import { PageHeader } from "../../components/layout/page-header";
import { Button, Stat, Status } from "../../components/ui/prototype";
import { useAuth } from "../auth/auth-context";
import { adminService, adminStore, isDemoAdmin } from "./admin-service";
import { auditStore } from "./audit-store";
import { AdminDataState, useAdminData } from "./console-pages";
import type { AuditEvent, MaintenanceStatus } from "../../types/admin";
import type { Page } from "../../types/api";

export function AuditLogPage() {
  const { user } = useAuth();
  const auditRevision = useSyncExternalStore(
    auditStore.subscribe,
    auditStore.getSnapshot,
  );
  const [search, setSearch] = useState("");
  const [action, setAction] = useState("");
  const [period, setPeriod] = useState("all");
  const [page, setPage] = useState(1);
  const load = useCallback(
    () =>
      adminService.listAudit(
        {
          page,
          page_size: 25,
          action: action || undefined,
          from:
            period === "all"
              ? undefined
              : new Date(Date.now() - Number(period) * 86400000).toISOString(),
        },
        user,
      ),
    [user, action, period, page],
  );
  const { data, loading, error, reload } = useAdminData<Page<AuditEvent>>(
    load,
    String(auditRevision),
  );
  const visible =
    data?.items.filter((item) =>
      `${item.actor_name ?? ""} ${item.action} ${item.resource_type} ${item.resource_id ?? ""}`
        .toLowerCase()
        .includes(search.toLowerCase()),
    ) ?? [];
  return (
    <>
      <PageHeader
        title="Audit log"
        eyebrow="ADMINISTRATION"
        description="Read-only history of security-sensitive changes."
      />
      <div className="toolbar">
        <input
          aria-label="Search audit log"
          placeholder="Search actor, action, or resource"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <select
          aria-label="Audit action"
          value={action}
          onChange={(event) => { setAction(event.target.value); setPage(1); }}
        >
          <option value="">All actions</option>
          <option value="deployment.">Deployments</option>
          <option value="user.">Users</option>
          <option value="provider_key.">Provider keys</option>
          <option value="token.">Tokens</option>
          <option value="maintenance.">Maintenance</option>
        </select>
        <select
          aria-label="Audit period"
          value={period}
          onChange={(event) => { setPeriod(event.target.value); setPage(1); }}
        >
          <option value="all">All time</option>
          <option value="7">Last 7 days</option>
          <option value="30">Last 30 days</option>
        </select>
      </div>
      {!data ? (
        <AdminDataState loading={loading} error={error} onRetry={reload} />
      ) : (
        <section className="panel table-panel" tabIndex={0} aria-label="Audit log table">
          <table>
            <thead>
              <tr>
                <th>TIME</th>
                <th>ACTOR</th>
                <th>ACTION</th>
                <th>RESOURCE</th>
                <th>REQUEST ID</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => (
                <tr key={item.id}>
                  <td>{new Date(item.created_at).toLocaleString()}</td>
                  <td>{item.actor_name ?? "System"}</td>
                  <td>
                    <code>{item.action}</code>
                  </td>
                  <td>
                    {item.resource_type} · {item.resource_id ?? "—"}
                  </td>
                  <td>
                    <code>{item.request_id ?? "—"}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!visible.length && (
            <p className="no-results">No audit events match these filters.</p>
          )}
        </section>
      )}
      {data && <div className="run-pagination"><span>{data.total} events · page {page}</span><div><Button secondary disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</Button><Button secondary disabled={page * 25 >= data.total} onClick={() => setPage(page + 1)}>Next</Button></div></div>}
      {error && data && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </>
  );
}

export function MaintenanceHealthPage() {
  const { user } = useAuth();
  const revision = useSyncExternalStore(
    adminStore.subscribe,
    adminStore.getSnapshot,
  );
  const [mutationError, setMutationError] = useState("");
  const [notice, setNotice] = useState("");
  const load = useCallback(() => adminService.maintenance(user), [user]);
  const { data, loading, error, reload } = useAdminData<MaintenanceStatus>(
    load,
    String(revision),
  );
  async function refresh() {
    try {
      await adminService.refreshViews(user);
      setNotice(
        isDemoAdmin
          ? "Prototype refresh recorded. No database views were changed."
          : "Analytics views refreshed.",
      );
      setMutationError("");
    } catch (cause) {
      setMutationError(
        cause instanceof Error ? cause.message : "Could not refresh views.",
      );
    }
  }
  return (
    <>
      <PageHeader
        title="Maintenance"
        eyebrow="ADMINISTRATION"
        description="Inspect service health and analytics maintenance."
      />
      {isDemoAdmin && (
        <p className="deployment-hint">
          Prototype status · API and database readiness cannot be verified until
          the backend is connected.
        </p>
      )}
      {mutationError && (
        <p className="form-error" role="alert">
          {mutationError}
        </p>
      )}
      {notice && (
        <p className="inline-feedback" role="status">
          {notice}
        </p>
      )}
      {!data ? (
        <AdminDataState loading={loading} error={error} onRetry={reload} />
      ) : (
        <>
          <div className="stats-grid">
            <Stat
              label="API"
              value={isDemoAdmin ? "Not connected" : data.api_status}
              note="Service readiness"
            />
            <Stat
              label="DATABASE"
              value={isDemoAdmin ? "Not connected" : data.database_status}
              note="Database readiness"
            />
            <Stat
              label="PARTITIONS"
              value={isDemoAdmin ? "—" : String(data.partition_count)}
              note="Available run partitions"
            />
            <Stat
              label="LAST REFRESH"
              value={
                data.last_view_refresh_at
                  ? new Date(data.last_view_refresh_at).toLocaleString()
                  : "Never"
              }
              note="Analytics views"
            />
          </div>
          <div className="dashboard-grid">
            <section className="panel">
              <div className="panel-head">
                <div>
                  <h2>System health</h2>
                  <p>Current service readiness.</p>
                </div>
              </div>
              <div className="health-row">
                <span>API</span>
                <Status
                  tone={data.api_status === "healthy" ? "success" : "warning"}
                >
                  {isDemoAdmin ? "Not connected" : data.api_status}
                </Status>
              </div>
              <div className="health-row">
                <span>Database</span>
                <Status
                  tone={
                    data.database_status === "healthy" ? "success" : "warning"
                  }
                >
                  {isDemoAdmin ? "Not connected" : data.database_status}
                </Status>
              </div>
              <div className="health-row">
                <span>Run partitions</span>
                <b>{isDemoAdmin ? "Unavailable" : data.partition_count}</b>
              </div>
            </section>
            <section className="panel">
              <div className="panel-head">
                <div>
                  <h2>Analytics views</h2>
                  <p>Refresh aggregate views after data changes.</p>
                </div>
              </div>
              <div className="health-row">
                <span>Last refresh</span>
                <b>
                  {data.last_view_refresh_at
                    ? new Date(data.last_view_refresh_at).toLocaleString()
                    : "Never"}
                </b>
              </div>
              <div className="maintenance-action">
                <Button onClick={refresh}>
                  {isDemoAdmin
                    ? "Record prototype refresh"
                    : "Refresh materialized views"}
                </Button>
              </div>
            </section>
          </div>
        </>
      )}
      {error && data && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </>
  );
}
