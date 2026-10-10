import { useLiveRefresh } from '../../lib/live-refresh';
import { useEffect, useState, useSyncExternalStore, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "../../components/layout/page-header";
import { Button, Field, Stat, Status } from "../../components/ui/prototype";
import { EmptyState } from "../../components/ui/empty-state";
import { useAuth } from "../auth/auth-context";
import { PromptDeploymentStatus } from "../versions/version-pages";
import type { Project } from "../../types/projects";
import {
  memberStore,
  projectFor,
  projectStore,
  promptStore,
  displayDate,
  workspaceService,
  workspaceStore,
} from "./workspace-data";

export function PromptRows({
  projectId,
  search = "",
}: {
  projectId?: string;
  search?: string;
}) {
  const prompts = promptStore.filter(
    (prompt) =>
      (!projectId || prompt.project_id === projectId) &&
      `${prompt.name} ${prompt.key}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  return !prompts.length ? (
    <div className="prompt-row no-results">No prompts match this search.</div>
  ) : (
    <div className="rows">
      {prompts.map((prompt) => (
        <Link
          className="prompt-row"
          key={prompt.id}
          to={`/prompts/${prompt.id}`}
        >
          <div>
            <code>{prompt.key}</code>
            <b>{prompt.name}</b>
          </div>
          <code className="version-code">v{prompt.latest_version_number}</code>
          <PromptDeploymentStatus promptId={prompt.id} />
          <span className="row-arrow">→</span>
        </Link>
      ))}
    </div>
  );
}
export function ProjectsPage() {
  const { user } = useAuth();
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const projects = projectStore.filter((project) =>
    `${project.name} ${project.key}`.toLowerCase().includes(search.toLowerCase()) &&
    (filter === "all" || (filter === "owned" ? project.owner_id === user?.id : project.owner_id !== user?.id)),
  );
  return (
    <>
      <PageHeader
        title="Projects"
        description="Organize prompts and collaborate with your team."
        action={
          <Link to="/projects/new">
            <Button>New project</Button>
          </Link>
        }
      />
      <div className="toolbar">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search projects"
          aria-label="Search projects"
        />
        <select aria-label="Project filter" value={filter} onChange={(event) => setFilter(event.target.value)}>
          <option value="all">All projects</option>
          <option value="owned">Owned by me</option>
          <option value="shared">Shared with me</option>
        </select>
      </div>
      <div className="project-grid">
        {projects.map((project) => (
          <Link
            className="project-card"
            key={project.id}
            to={`/projects/${project.id}`}
          >
            <div className="project-mark">{project.name[0]}</div>
            <div className="project-card-head">
              <h2>{project.name}</h2>
              <span>⋯</span>
            </div>
            <code>{project.key}</code>
            <p className="project-description">{project.description || "No description added."}</p>
            <p className="project-meta">
              {project.prompt_count} prompts · Updated{" "}
              {displayDate(project.updated_at)}
            </p>
            <div className="project-footer">
              <span>{project.member_count} members</span>
              <Status>Active</Status>
            </div>
          </Link>
        ))}
      </div>
      {!projects.length && <EmptyState title="No projects found" description="Try another search or create your first project." action={<Link to="/projects/new">Create project</Link>} />}
    </>
  );
}
export function NewProjectPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    const projectKey = key.trim().toLowerCase().replace(/\s+/g, "-");
    if (!name.trim() || !projectKey)
      return setError("Project name and key are required.");
    try {
      const project = await workspaceService.createProject({ name: name.trim(), key: projectKey, description: description.trim() || undefined }, user?.id ?? "");
      navigate(`/projects/${project.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create the project.");
    }
  }
  return (
    <>
      <PageHeader
        title="Create project"
        eyebrow="PROJECTS"
        description="Set up a workspace for your prompt library."
      />
      <form className="form-panel" onSubmit={submit}>
        {error && <p className="form-error" role="alert">{error}</p>}
        <Field
          label="Project name"
          placeholder="e.g. Customer Support"
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            if (!key)
              setKey(event.target.value.toLowerCase().replace(/\s+/g, "-"));
          }}
        />
        <Field
          label="Project key"
          placeholder="customer-support"
          value={key}
          onChange={(event) => setKey(event.target.value.replace(/\s/g, ""))}
        />
        <label className="field">
          <span>Description</span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="What will this project be used for?"
          />
        </label>
        <div className="form-actions">
          <Button secondary type="button" onClick={() => navigate("/projects")}>
            Cancel
          </Button>
          <Button type="submit">Create project</Button>
        </div>
      </form>
    </>
  );
}
export function ProjectDetailPage() {
  const { projectId } = useParams();
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot);
  const project = projectFor(projectId);
  if (!project) return <EmptyState title="Project not found" description="This project does not exist or is no longer available." action={<Link to="/projects">Back to projects</Link>} />;
  return <ProjectDetailContent key={project.id} project={project} />;
}
function ProjectDetailContent({ project }: { project: Project }) {
  const refresh = useLiveRefresh();
  const { user } = useAuth();
  const [tab, setTab] = useState<
    "overview" | "prompts" | "members" | "settings"
  >("overview");
  const members = memberStore[project.id] ?? [];
  const canManage = user?.role === "super_admin" || user?.id === project.owner_id;
  const [memberEmail, setMemberEmail] = useState("");
  const [draft, setDraft] = useState<{ baseName: string; baseDescription: string; name: string; description: string } | null>(null);
  const dirty = draft !== null && (draft.name !== draft.baseName || draft.description !== draft.baseDescription);
  const name = dirty ? draft.name : project.name;
  const description = dirty ? draft.description : project.description ?? "";
  const stale = dirty && (draft.baseName !== project.name || draft.baseDescription !== (project.description ?? ""));
  const editSettings = (changes: Partial<{ name: string; description: string }>) => setDraft({
    baseName: dirty ? draft.baseName : project.name, baseDescription: dirty ? draft.baseDescription : project.description ?? "",
    name, description, ...changes,
  });
  const [notice, setNotice] = useState("");
  const [settingsPending, setSettingsPending] = useState(false);
  useEffect(() => {
    let active = true;
    workspaceService.loadMembers(project.id)
      .catch((cause) => { if (active) setNotice(cause instanceof Error ? cause.message : "Could not load project members."); });
    return () => { active = false; };
  }, [project.id, refresh]);
  const projectPrompts = promptStore.filter(
    (prompt) => prompt.project_id === project.id,
  );
  async function addMember(event: FormEvent) {
    event.preventDefault();
    if (!canManage) return;
    const email = memberEmail.trim().toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(email))
      return setNotice("Enter a valid email address.");
    try {
      await workspaceService.addMember(project.id, { email });
      setMemberEmail("");
      setNotice(`${email} was added to the project.`);
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : "Could not add the member.");
    }
  }
  async function saveSettings(event: FormEvent) {
    event.preventDefault();
    if (!canManage || stale || settingsPending) return;
    if (!name.trim()) return setNotice("Project name is required.");
    setSettingsPending(true);
    try {
      await workspaceService.updateProject(project.id, { name: name.trim(), description: description.trim() || null }, user?.id ?? "");
      setDraft(null);
      setNotice("Project settings saved.");
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : "Could not save project settings.");
    } finally { setSettingsPending(false); }
  }
  return (
    <>
      <PageHeader
        title={project.name}
        eyebrow={`PROJECTS / ${project.key.toUpperCase()}`}
        description={
          project.description ?? "A workspace for your prompt library."
        }
        action={
          <Link to={`/prompts/new?project=${project.id}`}>
            <Button>New prompt</Button>
          </Link>
        }
      />
      <div className="tabs">
        {(["overview", "prompts", "members", "settings"] as const).map(
          (item) => (
            <button
              key={item}
              className={tab === item ? "selected" : ""}
              onClick={() => {
                setTab(item);
                setNotice("");
              }}
            >
              {item[0].toUpperCase() + item.slice(1)}{" "}
              {item === "prompts" && <span>{projectPrompts.length}</span>}
              {item === "members" && <span>{members.length}</span>}
            </button>
          ),
        )}
      </div>
      {notice && (
        <p className={/valid|already|required/i.test(notice) ? "inline-feedback error" : "inline-feedback"} role={/valid|already|required/i.test(notice) ? "alert" : "status"}>
          {notice}
        </p>
      )}
      {tab === "overview" && (
        <>
          <div className="detail-stats">
            <Stat
              label="PROMPTS"
              value={String(projectPrompts.length)}
              note="Reusable templates in this project"
            />
            <Stat
              label="VERSIONS"
              value={String(
                projectPrompts.reduce(
                  (sum, prompt) => sum + prompt.latest_version_number,
                  0,
                ),
              )}
              note="All versions immutable"
            />
            <Stat
              label="MEMBERS"
              value={String(members.length)}
              note="People with project access"
            />
          </div>
          <section className="panel">
            <div className="panel-head">
              <div>
                <h2>Prompt library</h2>
                <p>Reusable templates in this project.</p>
              </div>
              <button className="text-button" onClick={() => setTab("prompts")}>
                View all
              </button>
            </div>
            <PromptRows projectId={project.id} />
          </section>
        </>
      )}
      {tab === "prompts" && (
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Prompt library</h2>
              <p>{projectPrompts.length} templates in this project.</p>
            </div>
            <Link to={`/prompts/new?project=${project.id}`}>New prompt</Link>
          </div>
          <PromptRows projectId={project.id} />
        </section>
      )}
      {tab === "members" && (
        <section className="panel members-panel">
          <div className="panel-head">
            <div>
              <h2>Members</h2>
              <p>People who can access this project.</p>
            </div>
          </div>
          {canManage && <form className="member-add" onSubmit={addMember}>
            <input
              value={memberEmail}
              onChange={(event) =>
                setMemberEmail(event.target.value.replace(/\s/g, ""))
              }
              placeholder="teammate@company.com"
              aria-label="Member email"
            />
            <Button type="submit">Add member</Button>
          </form>}
          <div className="member-list">
            {members.map((member) => (
              <div className="member-row" key={member.user_id}>
                <div className="member-avatar">
                  {member.display_name.slice(0, 1).toUpperCase()}
                </div>
                <div>
                  <b>{member.display_name}</b>
                  <small>{member.email}</small>
                </div>
                <Status tone={member.role === "owner" ? "success" : "neutral"}>
                  {member.role}
                </Status>
                {canManage && member.role !== "owner" && (
                  <button
                    className="text-button danger"
                    onClick={async () => {
                      try {
                        await workspaceService.removeMember(project.id, member.user_id);
                        setNotice(`${member.display_name} was removed.`);
                      } catch (cause) {
                        setNotice(cause instanceof Error ? cause.message : "Could not remove the member.");
                      }
                    }}
                  >
                    Remove
                  </button>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
      {tab === "settings" && (
        <form className="form-panel" onSubmit={saveSettings}>
          {stale && <div role="alert"><p>Project settings changed. Your unsaved edits are preserved. Review the refreshed values before saving.</p><p>Current name: {project.name} · Current description: {project.description || "None"}</p>
            <Button secondary type="button" onClick={() => setDraft(null)}>Use refreshed settings</Button>
            <Button secondary type="button" onClick={() => setDraft({ baseName: project.name, baseDescription: project.description ?? "", name, description })}>Keep my edits</Button>
          </div>}
          <Field
            label="Project name"
            placeholder="Project name"
            value={name}
            onChange={(event) => editSettings({ name: event.target.value })} disabled={!canManage || settingsPending}
          />
          <label className="field">
            <span>Description</span>
            <textarea
              value={description}
              onChange={(event) => editSettings({ description: event.target.value })} disabled={!canManage || settingsPending}
            />
          </label>
          <div className="settings-key">
            <span>PROJECT KEY</span>
            <code>{project.key}</code>
            <small>Project keys cannot be changed after creation.</small>
          </div>
          <div className="form-actions">
            <Button type="submit" disabled={!canManage || stale || settingsPending}>Save settings</Button>
          </div>
        </form>
      )}
    </>
  );
}
