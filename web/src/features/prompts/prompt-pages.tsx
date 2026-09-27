import { useMemo, useState, type FormEvent } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { PageHeader } from "../../components/layout/page-header";
import { Button, Field, Status } from "../../components/ui/prototype";
import { EmptyState } from "../../components/ui/empty-state";
import type { Prompt } from "../../types/prompts";
import {
  projectStore,
  promptFor,
  promptStore,
  versionsFor,
  workspaceService,
} from "../projects/workspace-data";
import type { PromptVariable } from "../../types/prompts";

export function PromptsPage() {
  const [search, setSearch] = useState("");
  const [project, setProject] = useState("");
  const [environment, setEnvironment] = useState("");
  const filtered = useMemo(
    () =>
      promptStore.filter(
        (prompt) =>
          (!project || prompt.project_id === project) &&
          (!environment || prompt.active_environment === environment) &&
          `${prompt.name} ${prompt.key}`
            .toLowerCase()
            .includes(search.toLowerCase()),
      ),
    [search, project, environment],
  );
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
                <Status
                  tone={
                    prompt.active_environment === "production"
                      ? "success"
                      : "neutral"
                  }
                >
                  {prompt.active_environment}
                </Status>
                <span className="row-arrow">→</span>
              </Link>
            ))
          ) : (
            <EmptyState title="No prompts found" description="Try another filter or create a prompt." action={<Link to="/prompts/new">Create prompt</Link>} />
          )}
        </div>
      </section>
    </>
  );
}
export function NewPromptPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [projectId, setProjectId] = useState(
    params.get("project") ?? projectStore[0]?.id ?? "",
  );
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [template, setTemplate] = useState("");
  const [commit, setCommit] = useState("Initial prompt version");
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    const promptKey = key.trim().toLowerCase().replace(/\s+/g, "-");
    if (!projectId || !promptKey || !name.trim() || !template.trim())
      return setError("Project, key, name, and template are required.");
    try {
      const prompt = await workspaceService.createPrompt(projectId, {
        key: promptKey,
        name: name.trim(),
        description: description.trim() || undefined,
        template,
        variables: [],
        model_config: { provider: "mock", model: "deterministic-v1", temperature: 0, max_output_tokens: 500 },
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
            onChange={(event) => setTemplate(event.target.value)}
            placeholder="Write your prompt. Use {{variable_name}} for dynamic inputs."
          />
        </label>
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
  const { promptId } = useParams();
  const prompt = promptFor(promptId);
  if (!prompt) return <EmptyState title="Prompt not found" description="This prompt does not exist or is no longer available." action={<Link to="/prompts">Back to prompts</Link>} />;
  return <PromptDetailContent prompt={prompt} />;
}
function PromptDetailContent({ prompt }: { prompt: Prompt }) {
  const versions = versionsFor(prompt.id);
  const latest = versions[0];
  const [template, setTemplate] = useState(latest?.template ?? "");
  const [variables, setVariables] = useState<PromptVariable[]>(
    latest?.variables ?? [],
  );
  const [commit, setCommit] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  function addVariable() {
    setVariables([...variables, { name: "", description: "", required: true }]);
  }
  async function saveVersion() {
    if (!template.trim() || !commit.trim())
      return setNotice("Add a template and a commit message before saving.");
    if (!latest) return setNotice("The current version could not be loaded.");
    if (saving) return;
    setSaving(true);
    try {
      const version = await workspaceService.createVersion(prompt.id, {
        parent_version_id: latest.id,
        template,
        variables: variables.filter((variable) => variable.name.trim()),
        model_config: latest.model_config,
        commit_message: commit.trim(),
      });
      setCommit("");
      setNotice(`Version ${version.version_number} was saved as an immutable snapshot.`);
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : "Could not save the new version.");
    } finally {
      setSaving(false);
    }
  }
  return (
    <>
      <PageHeader
        title={prompt.name}
        eyebrow={`PROMPTS / ${prompt.key.toUpperCase()}`}
        description={prompt.description ?? "Reusable prompt template."}
        action={<Button onClick={saveVersion} disabled={saving}>{saving ? "Saving…" : "Save new version"}</Button>}
      />
      {notice && (
        <p className={/before saving|required/i.test(notice) ? "inline-feedback error" : "inline-feedback"} role={/before saving|required/i.test(notice) ? "alert" : "status"}>
          {notice}
        </p>
      )}
      <div className="detail-layout">
        <section className="panel editor">
          <div className="editor-top">
            <code>{prompt.key}</code>
            <Status
              tone={
                prompt.active_environment === "production"
                  ? "success"
                  : "neutral"
              }
            >
              {prompt.active_environment} v{prompt.latest_version_number}
            </Status>
          </div>
          <label className="field">
            <span>Prompt template</span>
            <textarea
              value={template}
              onChange={(event) => setTemplate(event.target.value)}
            />
          </label>
          <div className="variable-editor">
            <div className="panel-head">
              <div>
                <h2>Template variables</h2>
                <p>Values injected at run time.</p>
              </div>
              <button className="text-button" onClick={addVariable}>
                Add variable
              </button>
            </div>
            {variables.map((variable, index) => (
              <div className="variable-row" key={`${variable.name}-${index}`}>
                <input
                  value={variable.name}
                  onChange={(event) =>
                    setVariables(
                      variables.map((item, itemIndex) =>
                        itemIndex === index
                          ? {
                              ...item,
                              name: event.target.value.replace(/\s/g, ""),
                            }
                          : item,
                      ),
                    )
                  }
                  placeholder="variable_name"
                  aria-label="Variable name"
                />
                <input
                  value={variable.description ?? ""}
                  onChange={(event) =>
                    setVariables(
                      variables.map((item, itemIndex) =>
                        itemIndex === index
                          ? { ...item, description: event.target.value }
                          : item,
                      ),
                    )
                  }
                  placeholder="Description"
                  aria-label="Variable description"
                />
                <label className="check">
                  <input
                    type="checkbox"
                    checked={variable.required}
                    onChange={(event) =>
                      setVariables(
                        variables.map((item, itemIndex) =>
                          itemIndex === index
                            ? { ...item, required: event.target.checked }
                            : item,
                        ),
                      )
                    }
                  />
                  <span>Required</span>
                </label>
                <button
                  className="text-button danger"
                  onClick={() =>
                    setVariables(
                      variables.filter((_, itemIndex) => itemIndex !== index),
                    )
                  }
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
          <Field
            label="Commit message"
            placeholder="Explain this change"
            value={commit}
            onChange={(event) => setCommit(event.target.value)}
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
