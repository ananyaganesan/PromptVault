import { useLiveRefresh, refreshLiveData } from '../../lib/live-refresh';
import { useEffect, useState, useSyncExternalStore } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { PageHeader } from "../../components/layout/page-header";
import { Button, Status } from "../../components/ui/prototype";
import { EmptyState } from "../../components/ui/empty-state";
import {
  promptStore,
  workspaceStore,
  adaptVersion,
  versionsFor,
  versionEnvironments,
  promptEnvironments,
} from "../projects/workspace-data";
import { versionsApi, type BackendVersionDiff } from "./api";
import type { PromptVersion } from "../../types/versions";
import { useDemoData } from '../../lib/runtime';

export function PromptDeploymentStatus({ promptId }: { promptId: string }) {
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot);
  const environments = promptEnvironments(promptId);
  return <Status tone={environments?.includes('production') ? 'success' : 'neutral'}>{environments === undefined ? 'Deployment status unavailable' : environments.length ? `Active: ${environments.join(', ')}` : 'Draft'}</Status>;
}

export function VersionDeploymentStatus({ promptId, versionId }: { promptId: string; versionId: string }) {
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot);
  const environments = versionEnvironments(promptId, versionId);
  return <Status tone={environments?.includes('production') ? 'success' : 'neutral'}>{environments === undefined ? 'Deployment status unavailable' : environments.length ? `Active: ${environments.join(', ')}` : 'Not active'}</Status>;
}

function getVersion(versionId?: string) {
  for (const prompt of promptStore) {
    const version = versionsFor(prompt.id).find(
      (item) => item.id === versionId,
    );
    if (version) return { prompt, version, versions: versionsFor(prompt.id) };
  }
  return undefined;
}
type VersionResult = NonNullable<ReturnType<typeof getVersion>>;
function VersionMissing() { return <EmptyState title="Version not found" description="This version does not exist or is no longer available." action={<Link to="/prompts">Back to prompts</Link>} />; }
export function VersionDetailPage() {
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot);
  const { versionId } = useParams();
  const result = getVersion(versionId);
  return result ? <VersionDetailContent result={result} /> : <VersionMissing />;
}
function VersionDetailContent({ result: { prompt, version, versions } }: { result: VersionResult }) {
  const parent = versions.find((item) => item.id === version.parent_version_id);
  return (
    <>
      <PageHeader
        title={`Version ${version.version_number}`}
        eyebrow={`VERSIONS / ${prompt.key.toUpperCase()}`}
        description={`Immutable snapshot created by ${version.created_by_name}.`}
        action={
          <Link to={`/versions/${version.id}/compare`}>
            <Button secondary>Compare versions</Button>
          </Link>
        }
      />
      <div className="detail-layout">
        <section className="panel editor">
          <div className="editor-top">
            <code>commit: {version.commit_message}</code>
            <VersionDeploymentStatus promptId={prompt.id} versionId={version.id} />
          </div>
          <label className="field">
            <span>Template snapshot</span>
            <textarea value={version.template} readOnly />
          </label>
          <div className="editor-meta">
            <span>
              Parent version: {parent ? `v${parent.version_number}` : "None"}
            </span>
            <span>{version.variables.length} variables</span>
          </div>
        </section>
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Lineage</h2>
              <p>Version history remains immutable.</p>
            </div>
            <Link to={`/versions/${version.id}/lineage`}>Full lineage</Link>
          </div>
          {versions.map((item, index) => (
            <Link
              className="version-row"
              to={`/versions/${item.id}`}
              key={item.id}
            >
              <span
                className={
                  item.id === version.id
                    ? "timeline-dot current"
                    : "timeline-dot"
                }
              />
              <div>
                <b>
                  v{item.version_number}{" "}
                  {item.id === version.id ? "Current" : ""}
                </b>
                <small>
                  {item.commit_message} · {item.created_by_name}
                </small>
              </div>
              {index === 0 && <span>→</span>}
            </Link>
          ))}
        </section>
      </div>
    </>
  );
}
export function CompareVersionPage() {
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot);
  const { versionId } = useParams();
  const result = getVersion(versionId);
  return result ? <CompareVersionContent result={result} /> : <VersionMissing />;
}
function CompareVersionContent({ result: { prompt, version, versions } }: { result: VersionResult }) {
  const refresh = useLiveRefresh();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const defaultCompare =
    versions.find((item) => item.id === version.parent_version_id) ??
    versions.find((item) => item.id !== version.id) ??
    version;
  const requestedCompareId = searchParams.get("against");
  const compare =
    versions.find((item) => item.id === requestedCompareId && item.id !== version.id) ??
    defaultCompare;
  const requestKey = JSON.stringify([refresh, compare.id, version.id]);
  const [snapshot, setSnapshot] = useState<{ key: string; diff?: BackendVersionDiff; error?: string } | null>(null);
  const diff = snapshot?.key === requestKey ? snapshot.diff : undefined;
  const error = snapshot?.key === requestKey ? snapshot.error : undefined;
  useEffect(() => {
    if (useDemoData) return;
    if (compare.id === version.id) return;
    const controller = new AbortController();
    versionsApi.diff(version.id, compare.id, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setSnapshot({ key: requestKey, diff: value }); })
      .catch((cause) => { if (!controller.signal.aborted) setSnapshot({ key: requestKey, error: cause instanceof Error ? cause.message : "Could not compare versions." }); });
    return () => controller.abort();
  }, [requestKey, compare.id, version.id]);
  const variableDelta = diff ? diff.variables.added.length - diff.variables.removed.length : version.variables.length - compare.variables.length;
  return (
    <>
      <PageHeader
        title="Compare versions"
        eyebrow={`VERSIONS / ${prompt.key.toUpperCase()}`}
        description="Review changes between immutable prompt snapshots."
      />
      <section className="panel version-compare-controls" aria-label="Choose versions to compare">
        <label className="field">
          <span>Base version</span>
          <select
            aria-label="Base version"
            value={compare.id}
            onChange={(event) => {
              const next = new URLSearchParams(searchParams);
              next.set("against", event.target.value);
              setSearchParams(next, { replace: true });
            }}
            disabled={versions.length < 2}
          >
            {versions.map((item) => (
              <option key={item.id} value={item.id} disabled={item.id === version.id}>
                v{item.version_number} · {item.commit_message}
              </option>
            ))}
          </select>
        </label>
        <span className="version-compare-arrow" aria-hidden="true">→</span>
        <label className="field">
          <span>Compare version</span>
          <select
            aria-label="Compare version"
            value={version.id}
            onChange={(event) => {
              const next = new URLSearchParams(searchParams);
              next.set("against", compare.id);
              navigate(`/versions/${event.target.value}/compare?${next.toString()}`);
            }}
            disabled={versions.length < 2}
          >
            {versions.map((item) => (
              <option key={item.id} value={item.id} disabled={item.id === compare.id}>
                v{item.version_number} · {item.commit_message}
              </option>
            ))}
          </select>
        </label>
      </section>
      <div className="diff-summary">
        <Status>v{compare.version_number} base</Status>
        <span>→</span>
        <Status tone="success">v{version.version_number} selected</Status>
        <span>
          {variableDelta >= 0 ? "+" : ""}
          {variableDelta} variables
        </span>
      </div>
      {error && <p className="form-error" role="alert">{error} <Button secondary onClick={refreshLiveData}>Try again</Button></p>}
      <div className="detail-layout version-snapshot-layout">
        <section className="panel editor">
          <div className="editor-top">
            <code>v{compare.version_number}</code>
            <Status>Base</Status>
          </div>
          <label className="field">
            <span>Template snapshot</span>
            <textarea readOnly value={diff?.template_body.before ?? compare.template} />
          </label>
        </section>
        <section className="panel editor">
          <div className="editor-top">
            <code>v{version.version_number}</code>
            <Status tone="success">Selected</Status>
          </div>
          <label className="field">
            <span>Template snapshot</span>
            <textarea readOnly value={diff?.template_body.after ?? version.template} />
          </label>
        </section>
      </div>
    </>
  );
}
export function VersionLineagePage() {
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot);
  const { versionId } = useParams();
  const result = getVersion(versionId);
  return result ? <VersionLineageContent result={result} /> : <VersionMissing />;
}
function VersionLineageContent({ result: { prompt, version, versions } }: { result: VersionResult }) {
  const refresh = useLiveRefresh();
  const requestKey = JSON.stringify([refresh, version.id]);
  const [snapshot, setSnapshot] = useState<{ key: string; lineage?: PromptVersion[]; error?: string } | null>(null);
  const lineage = snapshot?.key === requestKey ? snapshot.lineage : undefined;
  const error = snapshot?.key === requestKey ? snapshot.error : undefined;
  useEffect(() => {
    if (useDemoData) return;
    const controller = new AbortController();
    versionsApi.lineage(version.id, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setSnapshot({ key: requestKey, lineage: value.items.map(adaptVersion), error: value.cycle_detected ? "A lineage cycle was detected." : "" });
      })
      .catch((cause) => { if (!controller.signal.aborted) setSnapshot({ key: requestKey, error: cause instanceof Error ? cause.message : "Could not load lineage." }); });
    return () => controller.abort();
  }, [requestKey, version.id]);
  const items = lineage ?? (useDemoData ? versions.filter((item) => item.version_number <= version.version_number) : []);
  return (
    <>
      <PageHeader
        title="Version lineage"
        eyebrow={`VERSIONS / ${prompt.key.toUpperCase()}`}
        description="Ordered ancestors for this immutable prompt version."
      />
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>{prompt.key}</h2>
            <p>
              v{version.version_number} descends through{" "}
              {Math.max(items.length - 1, 0)} earlier version
              {items.length === 2 ? "" : "s"}.
            </p>
          </div>
        </div>
        {error && <p className="form-error" role="alert">{error} <Button secondary onClick={refreshLiveData}>Try again</Button></p>}
        {!useDemoData && snapshot?.key !== requestKey && <p role="status">Loading lineage…</p>}
        {items.map((item) => (
          <Link
            className="version-row"
            to={`/versions/${item.id}`}
            key={item.id}
          >
            <span
              className={
                item.id === version.id ? "timeline-dot current" : "timeline-dot"
              }
            />
            <div>
              <b>
                v{item.version_number} · {item.commit_message}
              </b>
              <small>Created by {item.created_by_name}</small>
            </div>
            <span>→</span>
          </Link>
        ))}
      </section>
    </>
  );
}
