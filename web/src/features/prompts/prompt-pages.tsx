import { useProviderModels } from "../playground/provider-models";
import { LLM_PROVIDERS } from "../../lib/providers";
import { useMemo, useRef, useState, useSyncExternalStore, type FormEvent } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { PageHeader } from "../../components/layout/page-header";
import { Button, Field } from "../../components/ui/prototype";
import { EmptyState } from "../../components/ui/empty-state";
import { refreshLiveData } from "../../lib/live-refresh";
import { ApiClientError } from "../../lib/api/client";
import type { PromptVersion } from "../../types/versions";
import { VersionDeploymentStatus, PromptDeploymentStatus } from "../versions/version-pages";
import type { Prompt } from "../../types/prompts";
import {
  projectStore,
  promptEnvironments,
  promptFor,
  promptStore,
  versionsFor,
  workspaceService,
  workspaceStore,
} from "../projects/workspace-data";

const variableNamePattern = /^[A-Za-z_][A-Za-z0-9_]*$/;

function templateVariables(template: string): { names: string[]; error: string | null } {
  const names: string[] = [];
  const seen = new Set<string>();
  for (const match of template.matchAll(/\{\{(.*?)\}\}/g)) {
    const name = match[1].trim();
    if (!variableNamePattern.test(name)) {
      return { names, error: `Invalid variable "${name}". Use letters, numbers, and underscores, starting with a letter or underscore.` };
    }
    if (!seen.has(name)) {
      names.push(name);
      seen.add(name);
    }
  }
  return { names, error: null };
}

function TemplateVariablePreview({ names, error }: { names: string[]; error: string | null }) {
  return <section className="variable-editor" aria-label="Template variables">
    <div className="panel-head"><div><h2>Template variables</h2><p>Detected from placeholders in the template. Every variable needs a value when you run this version.</p></div></div>
    {error && <p className="form-error" role="alert">{error}</p>}
    {names.length ? <ul className="template-variable-list">{names.map((name) => <li key={name}><code>{name}</code></li>)}</ul> : <p className="template-variable-empty">No variables in this template.</p>}
  </section>;
}

export function PromptsPage() {
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot);
  const [search, setSearch] = useState("");
  const [project, setProject] = useState("");
  const [environment, setEnvironment] = useState("");
  const filtered = promptStore.filter(
        (prompt) =>
          (!project || prompt.project_id === project) &&
          (!environment || (environment === 'draft' ? promptEnvironments(prompt.id)?.length === 0 : promptEnvironments(prompt.id)?.includes(environment))) &&
          `${prompt.name} ${prompt.key}`
            .toLowerCase()
            .includes(search.toLowerCase()),
  );
  const hasFilters = Boolean(search.trim() || project || environment);
  return (
    <>
      <PageHeader
        title="Prompts"
        description="Reusable templates, versioned and ready to deploy."
        action={
          <Link to="/prompts/new">
            <Button>New prompt</Button>
          </Link>
        }
      />
      <div className="toolbar">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search prompts"
          aria-label="Search prompts"
        />
        <select
          value={project}
          onChange={(event) => setProject(event.target.value)}
          aria-label="Project"
        >
          <option value="">All projects</option>
          {projectStore.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <select
          value={environment}
          onChange={(event) => setEnvironment(event.target.value)}
          aria-label="Environment"
        >
          <option value="">All environments</option>
          <option value="draft">Draft</option>
          <option value="development">Development</option>
          <option value="staging">Staging</option>
          <option value="production">Production</option>
        </select>
      </div>
      <section className="panel">
        <div className="rows">
          {filtered.length ? (
            filtered.map((prompt) => (
              <Link
                className="prompt-row"
                key={prompt.id}
                to={`/prompts/${prompt.id}`}
              >
                <div>
                  <code>{prompt.key}</code>
                  <b>{prompt.name}</b>
                </div>
                <code className="version-code">
                  v{prompt.latest_version_number}
                </code>
                <PromptDeploymentStatus promptId={prompt.id} />
                <span className="row-arrow">→</span>
              </Link>
            ))
          ) : (
            <EmptyState title={hasFilters ? "No prompts match these filters" : "No prompts yet"} description={hasFilters ? "Try another search or filter." : "Create your first reusable prompt template."} action={!hasFilters && <Link to="/prompts/new">Create prompt</Link>} />
          )}
        </div>
      </section>
    </>
  );
}
export function NewPromptPage() {
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [projectId, setProjectId] = useState(
    params.get("project") ?? projectStore[0]?.id ?? "",
  );
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const testProvider = import.meta.env.DEV || import.meta.env.MODE === "test";
  const [provider, setProvider] = useState(testProvider ? "mock" : "gemini");
  const [model, setModel] = useState(testProvider ? "deterministic-v1" : "");
  const discovery = useProviderModels();
  const providerInfo = discovery.data?.items.find((item) => item.provider === provider);

  const [template, setTemplate] = useState("");
  const parsedVariables = useMemo(() => templateVariables(template), [template]);
  const [commit, setCommit] = useState("Initial prompt version");
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    const promptKey = key.trim().toLowerCase().replace(/\s+/g, "-");
    if (!projectId || !promptKey || !name.trim() || !template.trim())
      return setError("Project, key, name, and template are required.");
    if (parsedVariables.error) return setError(parsedVariables.error);
    try {
      const prompt = await workspaceService.createPrompt(projectId, {
        key: promptKey,
        name: name.trim(),
        description: description.trim() || undefined,
        template,
        model_config: { provider, model: model.trim(), temperature: 0, max_output_tokens: 500 },
        commit_message: commit || "Initial prompt version",
      });
      navigate(`/prompts/${prompt.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create the prompt.");
    }
  }
  return (
    <>
      <PageHeader
        title="Create prompt"
        eyebrow="PROMPTS"
        description="Create the first immutable version of a reusable template."
      />
      <form className="form-panel" onSubmit={submit}>
        {error && <p className="form-error" role="alert">{error}</p>}
        <label className="field">
          <span>LLM provider</span>
          <select value={provider} onChange={(event) => {
            setProvider(event.target.value);
            setModel(discovery.data?.items.find((item) => item.provider === event.target.value)?.models[0]?.id ?? "");
          }}>
            {LLM_PROVIDERS.map((name) => <option key={name} value={name}>{name}</option>)}
            {testProvider && <option value="mock">Mock (local testing)</option>}
          </select>
        </label>
        <label className="field">
          <span>Model identifier</span>
          {provider === "mock" ? <input value={model} readOnly required /> : <select value={model} onChange={(event) => setModel(event.target.value)} required>
            <option value="">Select a free-access model</option>
            {providerInfo?.models.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>}
          {provider !== "mock" && <p className="provider-note">{discovery.error || providerInfo?.quota_note || "Loading provider models…"}</p>}
        </label>
        <label className="field">
          <span>Project</span>
          <select
            value={projectId}
            onChange={(event) => setProjectId(event.target.value)}
          >
            {projectStore.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>
        <Field
          label="Prompt key"
          placeholder="e.g. checkout-reply"
          value={key}
          onChange={(event) => setKey(event.target.value.replace(/\s/g, ""))}
        />
        <Field
          label="Prompt name"
          placeholder="Customer checkout reply"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <label className="field">
          <span>Description</span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="What should this prompt help accomplish?"
          />
        </label>
        <label className="field">
          <span>Template</span>
          <textarea
            value={template}
            onChange={(event) => { setTemplate(event.target.value); setError(""); }}
            placeholder="Write your prompt. Use {{variable_name}} for dynamic inputs."
          />
        </label>
        <TemplateVariablePreview names={parsedVariables.names} error={parsedVariables.error} />
        <Field
          label="Commit message"
          placeholder="Initial prompt version"
          value={commit}
          onChange={(event) => setCommit(event.target.value)}
        />
        <div className="form-actions">
          <Button secondary type="button" onClick={() => navigate("/prompts")}>
            Cancel
          </Button>
          <Button type="submit">Create prompt</Button>
        </div>
      </form>
    </>
  );
}
export function PromptDetailPage() {
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot);
  const { promptId } = useParams();
  const prompt = promptFor(promptId);
  if (!prompt) return <EmptyState title="Prompt not found" description="This prompt does not exist or is no longer available." action={<Link to="/prompts">Back to prompts</Link>} />;
  return <PromptDetailContent key={prompt.id} prompt={prompt} />;
}
function PromptDetailContent({ prompt }: { prompt: Prompt }) {
  const versions = versionsFor(prompt.id);
  const latest = versions[0];
  const [draft, setDraft] = useState<{ base: PromptVersion; template: string } | null>(null);
  const [commit, setCommit] = useState("");
  const dirty = draft !== null && (draft.template !== draft.base.template || Boolean(commit.trim()));
  const template = dirty ? draft.template : latest?.template ?? "";
  const base = dirty ? draft.base : latest;
  const stale = Boolean(base && latest && base.id !== latest.id);
  const savingRef = useRef(false);
  const parsedVariables = templateVariables(template);
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  async function saveVersion() {
    if (!template.trim() || !commit.trim())
      return setNotice("Add a template and a commit message before saving.");
    if (parsedVariables.error) return setNotice(parsedVariables.error);
    if (!base) return setNotice("The current version could not be loaded.");
    if (stale || savingRef.current) return;
    savingRef.current = true;
    setSaving(true);
    try {
      const version = await workspaceService.createVersion(prompt.id, {
        parent_version_id: base.id,
        template,
        model_config: base.model_config,
        commit_message: commit.trim(),
      });
      setDraft({ base: version, template: version.template });
      setCommit("");
      setNotice(`Version ${version.version_number} was saved as an immutable snapshot.`);
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : "Could not save the new version.");
      if (cause instanceof ApiClientError && cause.status === 409) refreshLiveData();
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }
  return (
    <>
      <PageHeader
        title={prompt.name}
        eyebrow={`PROMPTS / ${prompt.key.toUpperCase()}`}
        description={prompt.description ?? "Reusable prompt template."}
        action={<Button onClick={saveVersion} disabled={saving || stale}>{saving ? "Saving…" : "Save new version"}</Button>}
      />
      {stale && <div role="alert"><p>A newer version is available. Your draft and commit message are preserved; review the latest version before choosing a parent.</p>
        <details><summary>View latest version {latest?.version_number}</summary><pre>{latest?.template}</pre><p>Model: {latest?.model_config.model}</p></details>
        <Button secondary disabled={saving} onClick={() => latest && setDraft({ base: latest, template })}>Keep draft with latest parent</Button>
        <Button secondary disabled={saving} onClick={() => latest && setDraft({ base: latest, template: latest.template })}>Replace draft with latest version</Button>
      </div>}
      {notice && (
        <p className={/before saving|required|invalid variable|could not/i.test(notice) ? "inline-feedback error" : "inline-feedback"} role={/before saving|required|invalid variable|could not/i.test(notice) ? "alert" : "status"}>
          {notice}
        </p>
      )}
      <div className="detail-layout">
        <section className="panel editor">
          <div className="editor-top">
            <code>{prompt.key}</code>
            {base && <VersionDeploymentStatus promptId={prompt.id} versionId={base.id} />}
          </div>
          <label className="field">
            <span>Prompt template</span>
            <textarea
              value={template}
              disabled={saving}
              onChange={(event) => { if (base) setDraft({ base, template: event.target.value }); setNotice(""); }}
            />
          </label>
          <TemplateVariablePreview names={parsedVariables.names} error={parsedVariables.error} />
          <Field
            label="Commit message"
            placeholder="Explain this change"
            value={commit}
            disabled={saving}
            onChange={(event) => { if (base && !dirty) setDraft({ base, template }); setCommit(event.target.value); }}
          />
        </section>
        <section className="panel version-panel">
          <div className="panel-head">
            <div>
              <h2>Version history</h2>
              <p>Immutable snapshots of this prompt.</p>
            </div>
            {latest && (
              <Link to={`/versions/${latest.id}/lineage`}>View lineage</Link>
            )}
          </div>
          {versions.map((version, index) => (
            <Link
              className="version-row"
              to={`/versions/${version.id}`}
              key={version.id}
            >
              <span
                className={
                  index === 0 ? "timeline-dot current" : "timeline-dot"
                }
              />
              <div>
                <b>
                  v{version.version_number} {index === 0 ? "Current" : ""}
                </b>
                <small>
                  {version.commit_message} · {version.created_by_name}
                </small>
              </div>
              <span>→</span>
            </Link>
          ))}
        </section>
      </div>
    </>
  );
}
