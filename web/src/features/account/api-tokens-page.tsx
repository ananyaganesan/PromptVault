import { useLiveRefresh, refreshLiveData } from '../../lib/live-refresh';
import {
  useEffect,
  useState,
  useSyncExternalStore,
  type FormEvent,
} from "react";
import { PageHeader } from "../../components/layout/page-header";
import { Button, Status } from "../../components/ui/prototype";
import { Modal } from "../../components/ui/modal";
import { ConfirmationDialog } from "../../components/ui/confirmation-dialog";
import { useAuth } from "../auth/auth-context";
import { projectStore } from "../projects/workspace-data";
import {
  deploymentStore,
  tokenService,
} from "../deployments/deployment-service";
import type { ApiTokenMetadata } from "../../types/deployments";

export function ApiTokensPage() {
  const refresh = useLiveRefresh();
  const [loading, setLoading] = useState(true);
  const { user } = useAuth();
  const revision = useSyncExternalStore(
    deploymentStore.subscribe,
    deploymentStore.getSnapshot,
  );
  const [items, setItems] = useState<ApiTokenMetadata[]>([]);
  const [name, setName] = useState("");
  const [projectId, setProjectId] = useState(projectStore[0]?.id ?? "");
  const [expiresAt, setExpiresAt] = useState("");
  const [issueOpen, setIssueOpen] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);
  const [revokeId, setRevokeId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [copyState, setCopyState] = useState("");
  useEffect(() => {
    let active = true;
    tokenService
      .list()
      .then((data) => {
        if (active) { setItems(data); setError(""); setLoading(false); }
      })
      .catch((cause) => {
        if (active) setLoading(false);
        if (active)
          setError(
            cause instanceof Error ? cause.message : "Could not load tokens.",
          );
      });
    return () => {
      active = false;
    };
  }, [revision, refresh]);
  async function issue(event: FormEvent) {
    event.preventDefault();
    try {
      const created = await tokenService.issue(
        { name, project_id: projectId, expires_at: expiresAt ? new Date(expiresAt).toISOString() : undefined },
        user,
      );
      setSecret(created.token);
      setIssueOpen(false);
      setName("");
      setExpiresAt("");
      setError("");
      setCopyState("");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not issue token.",
      );
    }
  }
  async function revoke() {
    if (!revokeId) return;
    try {
      await tokenService.revoke(revokeId, user);
      setRevokeId(null);
      setError("");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not revoke token.",
      );
      setRevokeId(null);
    }
  }
  async function copy() {
    if (!secret) return;
    try {
      await globalThis.navigator.clipboard.writeText(secret);
      setCopyState(
        "Copied. Keep this token somewhere secure; it cannot be shown again.",
      );
    } catch {
      setCopyState(
        "Copy unavailable. Select and copy the token manually before closing.",
      );
    }
  }
  return (
    <>
      <PageHeader
        title="API tokens"
        description="Create project-scoped credentials for the Serve API."
        action={
          <Button
            onClick={() => {
              setIssueOpen(true);
              setError("");
            }}
          >
            Issue token
          </Button>
        }
      />
      {error && (
        <p className="form-error" role="alert">
          {error} <Button secondary onClick={refreshLiveData}>Try again</Button>
        </p>
      )}
      {loading ? <p role="status">Loading API tokens…</p> : <section className="panel table-panel" tabIndex={0} aria-label="API tokens table">
        <table>
          <thead>
            <tr>
              <th>NAME</th>
              <th>PROJECT</th>
              <th>PREFIX</th>
              <th>CREATED</th>
              <th>EXPIRES</th>
              <th>STATUS</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.name}</td>
                <td>{item.project_name}</td>
                <td><code>{item.token_prefix}…</code></td>
                <td>{new Date(item.created_at).toLocaleDateString()}</td>
                <td>
                  {item.expires_at
                    ? new Date(item.expires_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                    : "Never"}
                </td>
                <td>
                  <Status tone={item.revoked_at || (item.expires_at && new Date(item.expires_at) <= new Date()) ? "neutral" : "success"}>
                    {item.revoked_at ? "Revoked" : item.expires_at && new Date(item.expires_at) <= new Date() ? "Expired" : "Active"}
                  </Status>
                </td>
                <td>
                  {!item.revoked_at && (
                    <button
                      className="text-button danger"
                      onClick={() => setRevokeId(item.id)}
                    >
                      Revoke
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!items.length && (
          <p className="no-results">No API tokens issued yet.</p>
        )}
      </section>}
      <Modal
        open={issueOpen}
        title="Issue API token"
        onClose={() => setIssueOpen(false)}
      >
        <form onSubmit={issue}>
          <label className="field">
            <span>Token name</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Production consumer"
              required
            />
          </label>
          <label className="field">
            <span>Project</span>
            <select
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
            >
              {projectStore.map((project) => (
                <option value={project.id} key={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Expiration</span>
            <input
              type="datetime-local"
              value={expiresAt}
              onChange={(event) => setExpiresAt(event.target.value)}
            />
          </label>
          <p className="deployment-hint">
            A token only grants runtime access to its selected project.
          </p>
          <div className="form-actions">
            <Button secondary type="button" onClick={() => setIssueOpen(false)}>
              Cancel
            </Button>
            <Button type="submit">Issue token</Button>
          </div>
        </form>
      </Modal>
      <Modal
        open={secret !== null}
        title="Save your API token"
        onClose={() => {
          setSecret(null);
          setCopyState("");
        }}
      >
        <p className="token-warning">
          Copy this token now. Once you close this dialog, the full value cannot
          be revealed again.
        </p>
        <label className="field">
          <span>New token</span>
          <input
            aria-label="New API token"
            readOnly
            value={secret ?? ""}
            onFocus={(event) => event.target.select()}
          />
        </label>
        {copyState && (
          <p role="status" className="deployment-hint">
            {copyState}
          </p>
        )}
        <div className="form-actions">
          <Button secondary onClick={copy}>
            Copy token
          </Button>
          <Button
            onClick={() => {
              setSecret(null);
              setCopyState("");
            }}
          >
            I saved it
          </Button>
        </div>
      </Modal>
      <ConfirmationDialog
        open={revokeId !== null}
        title="Revoke API token"
        message="Revoke this token? Applications using it will lose access immediately."
        onConfirm={revoke}
        onCancel={() => setRevokeId(null)}
      />
    </>
  );
}
