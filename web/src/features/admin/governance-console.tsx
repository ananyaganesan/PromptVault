import { LLM_PROVIDERS } from "../../lib/providers";
import {
  useCallback,
  useEffect,
  useState,
  useSyncExternalStore,
  type FormEvent,
} from "react";
import { PageHeader } from "../../components/layout/page-header";
import { Button, Stat, Status } from "../../components/ui/prototype";
import { Modal } from "../../components/ui/modal";
import { useAuth } from "../auth/auth-context";
import { projectStore } from "../projects/workspace-data";
import { runStore } from "../runs/run-service";
import { adminService, adminStore, isDemoAdmin } from "./admin-service";
import { auditStore } from "./audit-store";
import { budgetStore } from "./budget-store";
import { AdminDataState, useAdminData } from "./console-pages";
import type {
  AuditEvent,
  Budget,
  MaintenanceStatus,
  ModelPrice,
} from "../../types/admin";
import type { Page } from "../../types/api";

export function BudgetManagementPage() {
  const { user } = useAuth();
  const revision = useSyncExternalStore(
    adminStore.subscribe,
    adminStore.getSnapshot,
  );
  const budgetRevision = useSyncExternalStore(
    budgetStore.subscribe,
    budgetStore.getSnapshot,
  );
  const runRevision = useSyncExternalStore(
    runStore.subscribe,
    runStore.getSnapshot,
  );
  const [open, setOpen] = useState(false);
  const [targetType, setTargetType] = useState<"user" | "project">("project");
  const [targetId, setTargetId] = useState(projectStore[0]?.id ?? "");
  const [limit, setLimit] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [mutationError, setMutationError] = useState("");
  const [userTargets, setUserTargets] = useState<Array<{ id: string; name: string }>>([]);
  const [blockedRunCount, setBlockedRunCount] = useState(0);
  useEffect(() => {
    let active = true;
    adminService.listUsers({ page_size: 100 }, user).then((page) => {
      if (active) setUserTargets(page.items.map((item) => ({ id: item.id, name: item.display_name })));
    }).catch(() => undefined);
    return () => { active = false; };
  }, [user]);
  useEffect(() => {
    let active = true;
    adminService.listRuns({ status: "blocked", page: 1, page_size: 1 }, user).then((page) => {
      if (active) setBlockedRunCount(page.total);
    }).catch(() => undefined);
    return () => { active = false; };
  }, [revision, runRevision, user]);
  const load = useCallback(() => adminService.listBudgets(user), [user]);
  const { data, loading, error, reload } = useAdminData<Budget[]>(
    load,
    `${revision}:${budgetRevision}:${runRevision}`,
  );
  const targets =
    targetType === "project"
      ? projectStore.map((item) => ({ id: item.id, name: item.name }))
      : userTargets;
  const filtered =
    data?.filter(
      (item) =>
        item.target_name.toLowerCase().includes(search.toLowerCase()) &&
        (!filter || item.target_type === filter),
    ) ?? [];
  const totalLimit =
    data?.reduce((sum, item) => sum + Number(item.monthly_limit), 0) ?? 0;
  const totalSpend =
    data?.reduce((sum, item) => sum + Number(item.monthly_spend), 0) ?? 0;
  async function save(event: FormEvent) {
    event.preventDefault();
    try {
      await adminService.upsertBudget(
        { target_type: targetType, target_id: targetId, monthly_limit: limit },
        user,
      );
      setOpen(false);
      setMutationError("");
      setLimit("");
    } catch (cause) {
      setMutationError(
        cause instanceof Error ? cause.message : "Could not save budget.",
      );
    }
  }
  function selectType(value: "user" | "project") {
    setTargetType(value);
    setTargetId(
      value === "project" ? (projectStore[0]?.id ?? "") : (userTargets[0]?.id ?? ""),
    );
  }
  return (
    <>
      <PageHeader
        title="Budgets"
        eyebrow="ADMINISTRATION"
        description="Set monthly model spend limits for users and projects."
        action={<Button onClick={() => setOpen(true)}>Set budget</Button>}
      />
      {mutationError && (
        <p className="form-error" role="alert">
          {mutationError}
        </p>
      )}
      {!data ? (
        <AdminDataState loading={loading} error={error} onRetry={reload} />
      ) : (
        <>
          <div className="stats-grid">
            <Stat
              label="TOTAL LIMIT"
              value={`$${totalLimit.toFixed(4)}`}
              note="Across configured budgets"
            />
            <Stat
              label="USED"
              value={`$${totalSpend.toFixed(4)}`}
              note="User and project views"
            />
            <Stat
              label="NEAR LIMIT"
              value={String(
                data.filter(
                  (item) =>
                    Number(item.monthly_spend) >=
                    Number(item.monthly_limit) * 0.8,
                ).length,
              )}
              note="At least 80% used"
            />
            <Stat
              label="BLOCKED RUNS"
              value={String(blockedRunCount)}
              note="Current live ledger"
            />
          </div>
          <div className="toolbar">
            <input
              aria-label="Search budgets"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search budgets"
            />
            <select
              aria-label="Budget target filter"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            >
              <option value="">All targets</option>
              <option value="project">Projects</option>
              <option value="user">Users</option>
            </select>
          </div>
          <section className="panel table-panel" tabIndex={0} aria-label="Budget table">
            <table>
              <thead>
                <tr>
                  <th>TARGET</th>
                  <th>TYPE</th>
                  <th>MONTHLY LIMIT</th>
                  <th>SPEND</th>
                  <th>USED</th>
                  <th>STATE</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => {
                  const used =
                    Number(item.monthly_limit) > 0
                      ? Math.round(
                          (Number(item.monthly_spend) /
                            Number(item.monthly_limit)) *
                            100,
                        )
                      : 100;
                  return (
                    <tr key={item.id}>
                      <td>{item.target_name}</td>
                      <td>{item.target_type}</td>
                      <td>${item.monthly_limit}</td>
                      <td>${item.monthly_spend}</td>
                      <td>{used}%</td>
                      <td>
                        <Status tone={used >= 80 ? "warning" : "success"}>
                          {used >= 100
                            ? "At limit"
                            : used >= 80
                              ? "Near limit"
                              : "Healthy"}
                        </Status>
                      </td>
                      <td>
                        <button
                          className="text-button"
                          onClick={() => {
                            selectType(item.target_type);
                            setTargetId(item.target_id);
                            setLimit(item.monthly_limit);
                            setOpen(true);
                          }}
                        >
                          Edit
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!filtered.length && (
              <p className="no-results">No budgets match these filters.</p>
            )}
          </section>
        </>
      )}
      {error && data && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <Modal
        open={open}
        title="Set monthly budget"
        onClose={() => setOpen(false)}
      >
        <form onSubmit={save}>
          <label className="field">
            <span>Target type</span>
            <select
              value={targetType}
              onChange={(event) =>
                selectType(event.target.value as "user" | "project")
              }
            >
              <option value="project">Project</option>
              <option value="user">User</option>
            </select>
          </label>
          <label className="field">
            <span>Target</span>
            <select
              value={targetId}
              onChange={(event) => setTargetId(event.target.value)}
            >
              {targets.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Monthly limit (USD)</span>
            <input
              type="number"
              min="0"
              step="0.0001"
              value={limit}
              onChange={(event) => setLimit(event.target.value)}
              required
            />
          </label>
          <p className="deployment-hint">
            A run is blocked when its estimated cost exceeds either its user or
            project limit.
          </p>
          <div className="form-actions">
            <Button secondary type="button" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit">Save budget</Button>
          </div>
        </form>
      </Modal>
    </>
  );
}

export function PricingManagementPage() {
  const { user } = useAuth();
  const revision = useSyncExternalStore(
    adminStore.subscribe,
    adminStore.getSnapshot,
  );
  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState("gemini");
  const [model, setModel] = useState("");
  const [inputPrice, setInputPrice] = useState("");
  const [outputPrice, setOutputPrice] = useState("");
  const [effectiveDate, setEffectiveDate] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [mutationError, setMutationError] = useState("");
  const load = useCallback(() => adminService.listModelPrices(user), [user]);
  const { data, loading, error, reload } = useAdminData<ModelPrice[]>(
    load,
    String(revision),
  );
  async function save(event: FormEvent) {
    event.preventDefault();
    try {
      await adminService.addModelPrice(
        {
          provider,
          model,
          input_price_per_million: inputPrice,
          output_price_per_million: outputPrice,
          effective_from: new Date(`${effectiveDate}T00:00:00Z`).toISOString(),
        },
        user,
      );
      setOpen(false);
      setModel("");
      setInputPrice("");
      setOutputPrice("");
      setMutationError("");
    } catch (cause) {
      setMutationError(
        cause instanceof Error ? cause.message : "Could not add model price.",
      );
    }
  }
  return (
    <>
      <PageHeader
        title="Model pricing"
        eyebrow="ADMINISTRATION"
        description="Manage effective-dated prices used for run costs."
        action={<Button onClick={() => setOpen(true)}>Add price</Button>}
      />
      {mutationError && (
        <p className="form-error" role="alert">
          {mutationError}
        </p>
      )}
      {!data ? (
        <AdminDataState loading={loading} error={error} onRetry={reload} />
      ) : (
        <>
          <div className="stats-grid">
            <Stat
              label="ACTIVE MODELS"
              value={String(new Set(data.map((item) => item.model)).size)}
              note="Models with price records"
            />
            <Stat
              label="PRICE RECORDS"
              value={String(data.length)}
              note="History preserved"
            />
            <Stat label="CURRENCY" value="USD" note="Per million tokens" />
            <Stat
              label="SCHEDULED"
              value={String(
                data.filter(
                  (item) => new Date(item.effective_from) > new Date(),
                ).length,
              )}
              note="Future price changes"
            />
          </div>
          <section className="panel table-panel" tabIndex={0} aria-label="Pricing table">
            <table>
              <thead>
                <tr>
                  <th>PROVIDER</th>
                  <th>MODEL</th>
                  <th>TOKEN TYPE</th>
                  <th>PRICE / 1M</th>
                  <th>EFFECTIVE FROM</th>
                  <th>EFFECTIVE TO</th>
                </tr>
              </thead>
              <tbody>
                {data.map((item) => (
                  <tr key={item.id}>
                    <td>{item.provider}</td>
                    <td>{item.model}</td>
                    <td>{item.token_type}</td>
                    <td>${item.price_per_million_tokens}</td>
                    <td>
                      {new Date(item.effective_from).toLocaleDateString()}
                    </td>
                    <td>
                      {item.effective_to
                        ? new Date(item.effective_to).toLocaleDateString()
                        : "Current"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.length && (
              <p className="no-results">No model prices configured.</p>
            )}
          </section>
        </>
      )}
      {error && data && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <Modal open={open} title="Add model price" onClose={() => setOpen(false)}>
        <form onSubmit={save}>
          <label className="field">
            <span>Provider</span>
            <select value={provider} onChange={(event) => setProvider(event.target.value)}>
              {LLM_PROVIDERS.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Model</span>
            <input
              value={model}
              onChange={(event) => setModel(event.target.value)}
              required
            />
          </label>
          <label className="field">
            <span>Input price per million tokens</span>
            <input
              type="number"
              min="0"
              step="0.000001"
              value={inputPrice}
              onChange={(event) => setInputPrice(event.target.value)}
              required
            />
          </label>
          <label className="field">
            <span>Output price per million tokens</span>
            <input
              type="number"
              min="0"
              step="0.000001"
              value={outputPrice}
              onChange={(event) => setOutputPrice(event.target.value)}
              required
            />
          </label>
          <label className="field">
            <span>Effective from</span>
            <input
              type="date"
              value={effectiveDate}
              onChange={(event) => setEffectiveDate(event.target.value)}
              required
            />
          </label>
          <div className="form-actions">
            <Button secondary type="button" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit">Add price</Button>
          </div>
        </form>
      </Modal>
    </>
  );
}

export function AuditLogPage() {
  const { user } = useAuth();
  const auditRevision = useSyncExternalStore(
    auditStore.subscribe,
    auditStore.getSnapshot,
  );
  const [search, setSearch] = useState("");
  const [action, setAction] = useState("");
  const [period, setPeriod] = useState("all");
  const load = useCallback(
    () =>
      adminService.listAudit(
        {
          page_size: 100,
          action: action || undefined,
          from:
            period === "all"
              ? undefined
              : new Date(Date.now() - Number(period) * 86400000).toISOString(),
        },
        user,
      ),
    [user, action, period],
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
          onChange={(event) => setAction(event.target.value)}
        >
          <option value="">All actions</option>
          <option value="deployment.">Deployments</option>
          <option value="user.">Users</option>
          <option value="provider_key.">Provider keys</option>
          <option value="budget.">Budgets</option>
          <option value="model_price.">Pricing</option>
          <option value="token.">Tokens</option>
          <option value="maintenance.">Maintenance</option>
        </select>
        <select
          aria-label="Audit period"
          value={period}
          onChange={(event) => setPeriod(event.target.value)}
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
