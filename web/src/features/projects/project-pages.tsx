import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "../../components/layout/page-header";
import { Button, Field, Stat, Status } from "../../components/ui/prototype";
import { EmptyState } from "../../components/ui/empty-state";
import { useAuth } from "../auth/auth-context";
import type { Project } from "../../types/projects";
import {
  memberStore,
  projectFor,
  projectStore,
  displayDate,
} from "./workspace-data";

export function ProjectsPage() {
  const { user } = useAuth();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const projects = useMemo(
    () =>
      projectStore.filter((project) =>
        `${project.name} ${project.key}`.toLowerCase().includes(search.toLowerCase()) &&
        (filter === "all" || (filter === "owned" ? project.owner_id === user?.id : project.owner_id !== user?.id)),
      ),
    [search, filter, user?.id],
  );
  return (
    <>
      <PageHeader
        title="Projects"
        description="Organize workspaces and collaborate with your team."
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
            <p>Updated {displayDate(project.updated_at)}</p>
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
  function submit(event: FormEvent) {
    event.preventDefault();
    const projectKey = key.trim().toLowerCase().replace(/\s+/g, "-");
    if (!name.trim() || !projectKey)
      return setError("Project name and key are required.");
    if (projectStore.some((project) => project.key === projectKey))
      return setError("That project key is already in use.");
    const id = `${projectKey}-${Date.now()}`;
    projectStore.unshift({
      id,
      key: projectKey,
      name: name.trim(),
      description: description.trim() || null,
      prompt_count: 0,
      member_count: 1,
      monthly_spend: "$0.00",
      updated_at: new Date().toISOString(),
      is_owner: true,
      created_at: new Date().toISOString(),
      owner_id: user?.id ?? "",
    });
    memberStore[id] = [
      {
        user_id: user?.id ?? "",
        display_name: user?.display_name ?? "Unknown user",
        email: user?.email ?? "",
        role: "owner",
        joined_at: new Date().toISOString(),
      },
    ];
    navigate(`/projects/${id}`);
  }
  return (
    <>
      <PageHeader
        title="Create project"
        eyebrow="PROJECTS"
        description="Set up a workspace for your team."
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
  const project = projectFor(projectId);
  if (!project) return <EmptyState title="Project not found" description="This project does not exist or is no longer available." action={<Link to="/projects">Back to projects</Link>} />;
  return <ProjectDetailContent project={project} />;
}
function ProjectDetailContent({ project }: { project: Project }) {
  const [tab, setTab] = useState<"overview" | "members" | "settings">("overview");
  const [members, setMembers] = useState(memberStore[project.id] ?? []);
  const [memberEmail, setMemberEmail] = useState("");
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description ?? "");
  const [notice, setNotice] = useState("");
  function addMember(event: FormEvent) {
    event.preventDefault();
    const email = memberEmail.trim().toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(email))
      return setNotice("Enter a valid email address.");
    if (members.some((member) => member.email === email))
      return setNotice("This person is already a member.");
    const member = {
      user_id: `member-${Date.now()}`,
      display_name: email.split("@")[0],
      email,
      role: "member" as const,
      joined_at: new Date().toISOString(),
    };
    const next = [...members, member];
    setMembers(next);
    memberStore[project.id] = next;
    project.member_count = next.length;
    setMemberEmail("");
    setNotice(`${email} was added to the project.`);
  }
  function saveSettings(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return setNotice("Project name is required.");
    project.name = name.trim();
    project.description = description.trim() || null;
    project.updated_at = new Date().toISOString();
    setNotice("Project settings saved.");
  }
  return (
    <>
      <PageHeader
        title={project.name}
        eyebrow={`PROJECTS / ${project.key.toUpperCase()}`}
        description={project.description ?? "A workspace for your team."}
      />
      <div className="tabs">
        {(["overview", "members", "settings"] as const).map(
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
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Project overview</h2>
              <p>Manage members and workspace settings from this project.</p>
            </div>
          </div>
          <div className="detail-stats">
            <Stat label="MEMBERS" value={String(members.length)} note="People with project access" />
            <Stat label="STATUS" value="Active" note="Workspace is available" />
          </div>
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
          <form className="member-add" onSubmit={addMember}>
            <input
              value={memberEmail}
              onChange={(event) =>
                setMemberEmail(event.target.value.replace(/\s/g, ""))
              }
              placeholder="teammate@company.com"
              aria-label="Member email"
            />
            <Button type="submit">Add member</Button>
          </form>
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
                {member.role !== "owner" && (
                  <button
                    className="text-button danger"
                    onClick={() => {
                      const next = members.filter(
                        (item) => item.user_id !== member.user_id,
                      );
                      setMembers(next);
                      memberStore[project.id] = next;
                      project.member_count = next.length;
                      setNotice(`${member.display_name} was removed.`);
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
          <Field
            label="Project name"
            placeholder="Project name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <label className="field">
            <span>Description</span>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>
          <div className="settings-key">
            <span>PROJECT KEY</span>
            <code>{project.key}</code>
            <small>Project keys cannot be changed after creation.</small>
          </div>
          <div className="form-actions">
            <Button type="submit">Save settings</Button>
          </div>
        </form>
      )}
    </>
  );
}
