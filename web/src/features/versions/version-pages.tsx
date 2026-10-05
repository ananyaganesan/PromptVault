import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PageHeader } from "../../components/layout/page-header";
import { Button, Status } from "../../components/ui/prototype";
import { EmptyState } from "../../components/ui/empty-state";
import {
  promptStore,
  adaptVersion,
  versionsFor,
} from "../projects/workspace-data";
import { versionsApi, type BackendVersionDiff } from "./api";
import type { PromptVersion } from "../../types/versions";
import { useDemoData } from '../../lib/runtime';

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
            <Status tone="success">{prompt.active_environment}</Status>
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
  const { versionId } = useParams();
  const result = getVersion(versionId);
  return result ? <CompareVersionContent result={result} /> : <VersionMissing />;
}
function CompareVersionContent({ result: { prompt, version, versions } }: { result: VersionResult }) {
  const compare =
    versions.find((item) => item.id === version.parent_version_id) ??
    versions[1] ??
    version;
  const [diff, setDiff] = useState<BackendVersionDiff | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (useDemoData) return;
    if (compare.id === version.id) return;
    const controller = new AbortController();
    versionsApi.diff(version.id, compare.id, controller.signal)
      .then((value) => { setDiff(value); setError(""); })
      .catch((cause) => { if (cause instanceof Error && cause.name !== "AbortError") setError(cause.message); });
    return () => controller.abort();
  }, [compare.id, version.id]);
  const variableDelta = diff ? diff.variables.added.length - diff.variables.removed.length : version.variables.length - compare.variables.length;
  return (
    <>
      <PageHeader
        title="Compare versions"
        eyebrow={`VERSIONS / ${prompt.key.toUpperCase()}`}
        description="Review changes between immutable prompt snapshots."
      />
      <div className="diff-summary">
        <Status>v{compare.version_number} base</Status>
        <span>→</span>
        <Status tone="success">v{version.version_number} selected</Status>
        <span>
          {variableDelta >= 0 ? "+" : ""}
          {variableDelta} variables
        </span>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="detail-layout">
        <section className="panel editor">
          <div className="editor-top">
            <code>v{compare.version_number}</code>
            <Status>Previous</Status>
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
  const { versionId } = useParams();
  const result = getVersion(versionId);
  return result ? <VersionLineageContent result={result} /> : <VersionMissing />;
}
function VersionLineageContent({ result: { prompt, version, versions } }: { result: VersionResult }) {
  const [lineage, setLineage] = useState<PromptVersion[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (useDemoData) return;
    const controller = new AbortController();
    versionsApi.lineage(version.id, controller.signal)
      .then((value) => {
        setLineage(value.items.map(adaptVersion));
        setError(value.cycle_detected ? "A lineage cycle was detected." : "");
      })
      .catch((cause) => { if (cause instanceof Error && cause.name !== "AbortError") setError(cause.message); });
    return () => controller.abort();
  }, [version.id]);
  const items = lineage ?? versions.filter((item) => item.version_number <= version.version_number);
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
        {error && <p className="form-error" role="alert">{error}</p>}
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
