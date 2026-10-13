import type { AddProjectMemberRequest, CreateProjectRequest, Project, ProjectMember, UpdateProjectRequest } from '../../types/projects'
import type { CreatePromptRequest, Prompt, PromptVariable } from '../../types/prompts'
import type { CreateVersionRequest, PromptVersion } from '../../types/versions'
import type { Page } from '../../types/api'
import { apiClient } from '../../lib/api/client'
import { useDemoData } from '../../lib/runtime'
import { refreshLiveData } from '../../lib/live-refresh'
import { readAllPages } from '../../lib/api/pagination'

export const projectStore: Project[] = [
  { id: 'checkout', key: 'checkout-assistant', name: 'Checkout Assistant', description: 'Prompts for the checkout support experience.', prompt_count: 3, member_count: 5, monthly_spend: '$0.0140', updated_at: '2025-08-28T10:30:00Z', is_owner: true, created_at: '2025-08-01T09:00:00Z', owner_id: 'usr_demo_admin' },
  { id: 'growth', key: 'growth-tools', name: 'Growth Tools', description: 'Experiment prompts for the growth team.', prompt_count: 0, member_count: 1, monthly_spend: '$0.0000', updated_at: '2025-08-27T11:00:00Z', is_owner: true, created_at: '2025-07-10T09:00:00Z', owner_id: 'usr_demo_admin' },
  { id: 'support', key: 'internal-support', name: 'Internal Support', description: 'Internal support helpers and triage.', prompt_count: 0, member_count: 1, monthly_spend: '$0.0000', updated_at: '2025-08-24T11:00:00Z', is_owner: false, created_at: '2025-07-01T09:00:00Z', owner_id: 'sam' },
]

export const memberStore: Record<string, ProjectMember[]> = {
  checkout: [
    { user_id: 'usr_demo_admin', display_name: 'Alex Morgan', email: 'admin@promptvault.dev', role: 'owner', joined_at: '2025-08-01T09:00:00Z' },
    { user_id: 'usr_demo_user', display_name: 'Jamie Chen', email: 'user@promptvault.dev', role: 'member', joined_at: '2025-08-01T10:00:00Z' },
    { user_id: 'ananya', display_name: 'Ananya Ganesan', email: 'ananya@promptvault.dev', role: 'member', joined_at: '2025-08-02T09:00:00Z' },
    { user_id: 'jobin', display_name: 'Jobin Thomas', email: 'jobin@promptvault.dev', role: 'member', joined_at: '2025-08-04T09:00:00Z' },
    { user_id: 'sam', display_name: 'Sam Rivera', email: 'sam@promptvault.dev', role: 'member', joined_at: '2025-08-05T09:00:00Z' },
  ],
  growth: [{ user_id: 'usr_demo_admin', display_name: 'Alex Morgan', email: 'admin@promptvault.dev', role: 'owner', joined_at: '2025-07-10T09:00:00Z' }],
  support: [{ user_id: 'sam', display_name: 'Sam Rivera', email: 'sam@promptvault.dev', role: 'owner', joined_at: '2025-07-01T09:00:00Z' }],
}

const checkoutVariables: PromptVariable[] = [
  { name: 'customer_message', description: 'The customer’s checkout question.', required: true },
  { name: 'order_context', description: 'Relevant order status and payment context.', required: false, default_value: 'No order context provided.' },
]

export const promptStore: Prompt[] = [
  { id: 'checkout-reply', project_id: 'checkout', key: 'checkout-reply', name: 'Customer checkout reply', description: 'Answer customer questions about checkout with a clear, friendly tone.', latest_version_number: 3, active_environment: 'staging', updated_at: '2025-08-28T10:30:00Z', created_at: '2025-08-18T09:00:00Z' },
  { id: 'order-status', project_id: 'checkout', key: 'order-status', name: 'Order status assistant', description: 'Explain order status in helpful, plain language.', latest_version_number: 2, active_environment: 'production', updated_at: '2025-08-27T10:00:00Z', created_at: '2025-08-14T09:00:00Z' },
  { id: 'refund-policy', project_id: 'checkout', key: 'refund-policy', name: 'Refund policy response', description: 'Give a concise response about refund eligibility.', latest_version_number: 1, active_environment: 'draft', updated_at: '2025-08-23T10:00:00Z', created_at: '2025-08-23T09:00:00Z' },
]

export const versionStore: Record<string, PromptVersion[]> = {
  'checkout-reply': [
    { id: 'checkout-v3', prompt_id: 'checkout-reply', version_number: 3, parent_version_id: 'checkout-v2', template: 'You are a helpful checkout support assistant.\n\nCustomer message:\n{{customer_message}}\n\nOrder context:\n{{order_context}}\n\nRespond with a concise, reassuring answer.', variables: checkoutVariables, model_config: { provider: 'mock', model: 'deterministic-v1', temperature: 0.3, max_output_tokens: 300 }, commit_message: 'Add order context variable', created_by: 'alex', created_by_name: 'Alex Morgan', created_at: '2025-08-28T10:30:00Z' },
    { id: 'checkout-v2', prompt_id: 'checkout-reply', version_number: 2, parent_version_id: 'checkout-v1', template: 'You are a helpful checkout support assistant.\n\nCustomer message:\n{{customer_message}}\n\nRespond with a clear, reassuring answer.', variables: [checkoutVariables[0]], model_config: { provider: 'mock', model: 'deterministic-v1', temperature: 0.3, max_output_tokens: 300 }, commit_message: 'Improve tone instructions', created_by: 'ananya', created_by_name: 'Ananya Ganesan', created_at: '2025-08-24T10:30:00Z' },
    { id: 'checkout-v1', prompt_id: 'checkout-reply', version_number: 1, parent_version_id: null, template: 'Answer this customer checkout question:\n{{customer_message}}', variables: [checkoutVariables[0]], model_config: { provider: 'mock', model: 'deterministic-v1', temperature: 0.5, max_output_tokens: 200 }, commit_message: 'Initial prompt version', created_by: 'alex', created_by_name: 'Alex Morgan', created_at: '2025-08-18T09:00:00Z' },
  ],
}

export function displayDate(value: string) { return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value)) }
export function projectFor(id?: string) { return projectStore.find((project) => project.id === id) }
export function promptFor(id?: string) { return promptStore.find((prompt) => prompt.id === id) }
export function versionsFor(promptId: string) { return versionStore[promptId] ?? [] }

type BackendProject = {
  id: string
  name: string
  key: string
  description: string | null
  owner: { id: string; display_name: string }
  member_count: number
  prompt_count: number
  created_at: string
  updated_at: string
}

type BackendPrompt = {
  id: string
  project_id: string
  key: string
  name: string
  description: string | null
  latest_version_number: number
  created_at: string
  updated_at: string
}

type BackendPromptDetail = Omit<BackendPrompt, 'latest_version_number'> & {
  latest_version: BackendVersion
  active_versions: Record<string, string>
}

export type BackendVersion = {
  id: string
  prompt_id: string
  version_number: number
  parent_version_id: string | null
  template_body: string
  variables: string[]
  model_config: PromptVersion['model_config']
  commit_message: string
  created_by: { id: string; display_name: string }
  created_at: string
}

type BackendMember = {
  id: string
  email: string
  display_name: string
  role: 'user' | 'admin'
  is_active: boolean
  created_at: string
  is_owner: boolean
}

let revision = 0
let loadGeneration = 0
const memberGenerations = new Map<string, number>()
export const activeVersionsStore: Record<string, Record<string, string>> = {}
export function promptEnvironments(promptId: string): string[] | undefined {
  const active = activeVersionsStore[promptId]
  return active ? Object.keys(active).map((environment) => environment === 'prod' ? 'production' : environment === 'dev' ? 'development' : environment) : undefined
}
export function versionEnvironments(promptId: string, versionId: string): string[] | undefined {
  const active = activeVersionsStore[promptId]
  return active ? Object.entries(active).filter(([, id]) => id === versionId).map(([environment]) => environment === 'prod' ? 'production' : environment === 'dev' ? 'development' : environment) : undefined
}
const listeners = new Set<() => void>()
function notify() { revision += 1; listeners.forEach((listener) => listener()) }
function notifyMutation() { loadGeneration += 1; notify() }
function replaceArray<T>(target: T[], values: T[]) { target.splice(0, target.length, ...values) }

export async function collectPages<T>(
  loadPage: (page: number, pageSize: number) => Promise<Page<T>>,
  pageSize = 100,
): Promise<T[]> {
  return readAllPages((page) => loadPage(page, pageSize))
}

async function loadAllPages<T>(path: string, query: Record<string, string> = {}): Promise<T[]> {
  return collectPages((page, pageSize) => apiClient.request<Page<T>>(path, {
    query: { ...query, page, page_size: pageSize },
  }))
}

function adaptProject(project: BackendProject, userId: string): Project {
  return {
    id: project.id,
    key: project.key,
    name: project.name,
    description: project.description,
    prompt_count: project.prompt_count,
    member_count: project.member_count,
    monthly_spend: '0',
    updated_at: project.updated_at,
    is_owner: project.owner.id === userId,
    created_at: project.created_at,
    owner_id: project.owner.id,
  }
}

function adaptPrompt(prompt: BackendPrompt): Prompt {
  return { ...prompt, active_environment: 'draft' }
}

function activeEnvironment(activeVersions: Record<string, string>): Prompt['active_environment'] {
  if (activeVersions.prod) return 'production'
  if (activeVersions.staging) return 'staging'
  if (activeVersions.dev) return 'development'
  return 'draft'
}

function adaptPromptDetail(prompt: BackendPromptDetail): Prompt {
  return {
    id: prompt.id,
    project_id: prompt.project_id,
    key: prompt.key,
    name: prompt.name,
    description: prompt.description,
    latest_version_number: prompt.latest_version.version_number,
    active_environment: activeEnvironment(prompt.active_versions),
    created_at: prompt.created_at,
    updated_at: prompt.updated_at,
  }
}

export function adaptVersion(version: BackendVersion): PromptVersion {
  return {
    id: version.id,
    prompt_id: version.prompt_id,
    version_number: version.version_number,
    parent_version_id: version.parent_version_id,
    template: version.template_body,
    variables: version.variables.map((name) => ({ name, required: true })),
    model_config: version.model_config,
    commit_message: version.commit_message,
    created_by: version.created_by.id,
    created_by_name: version.created_by.display_name,
    created_at: version.created_at,
  }
}

function adaptMember(member: BackendMember): ProjectMember {
  return {
    user_id: member.id,
    display_name: member.display_name,
    email: member.email,
    role: member.is_owner ? 'owner' : 'member',
    joined_at: member.created_at,
  }
}

function replaceProject(project: Project) {
  const index = projectStore.findIndex((item) => item.id === project.id)
  if (index === -1) projectStore.unshift(project)
  else projectStore[index] = project
}

function replacePrompt(prompt: Prompt) {
  const index = promptStore.findIndex((item) => item.id === prompt.id)
  if (index === -1) promptStore.unshift(prompt)
  else promptStore[index] = prompt
}

export const workspaceStore = {
  subscribe(listener: () => void) { listeners.add(listener); return () => listeners.delete(listener) },
  getSnapshot() { return revision },
}

export const workspaceService = {
  async load(userId: string) {
    if (useDemoData) { notify(); return }
    const generation = ++loadGeneration
    const projects = await loadAllPages<BackendProject>('/projects')
    const nextProjects = projects.map((project) => adaptProject(project, userId))
    const nextPrompts: Prompt[] = []
    const nextVersions: Record<string, PromptVersion[]> = {}
    for (const project of nextProjects) {
      const prompts = await loadAllPages<BackendPrompt>(`/projects/${project.id}/prompts`)
      for (const prompt of prompts) {
        nextPrompts.push(adaptPrompt(prompt))
        const versions = await loadAllPages<BackendVersion>(`/prompts/${prompt.id}/versions`)
        nextVersions[prompt.id] = versions.map(adaptVersion)
      }
    }
    const nextActive: Record<string, Record<string, string>> = Object.fromEntries(nextPrompts.map((prompt) => [prompt.id, {}]))
    if (nextPrompts.length) {
      const active = await loadAllPages<{ prompt_id: string; environment: string; version_id: string }>('/deployments', { status: 'active' })
      for (const deployment of active) {
        if (nextActive[deployment.prompt_id]) nextActive[deployment.prompt_id][deployment.environment] = deployment.version_id
      }
      for (const prompt of nextPrompts) {
        prompt.active_environment = activeEnvironment(Object.fromEntries(
          active.filter((deployment) => deployment.prompt_id === prompt.id).map((deployment) => [deployment.environment, 'active']),
        ))
      }
    }
    // An earlier session/request must never overwrite a newer workspace snapshot.
    if (generation !== loadGeneration) return
    for (const key of Object.keys(activeVersionsStore)) delete activeVersionsStore[key]
    Object.assign(activeVersionsStore, nextActive)
    replaceArray(projectStore, nextProjects)
    replaceArray(promptStore, nextPrompts)
    for (const key of Object.keys(versionStore)) delete versionStore[key]
    Object.assign(versionStore, nextVersions)
    for (const key of Object.keys(memberStore)) {
      if (!nextProjects.some((project) => project.id === key)) delete memberStore[key]
    }
    notify()
  },
  async createProject(request: CreateProjectRequest, userId: string) {
    if (useDemoData) {
      const createdAt = new Date().toISOString()
      const project: Project = { id: `project-${Date.now()}`, key: request.key, name: request.name, description: request.description ?? null, prompt_count: 2, member_count: 1, monthly_spend: '$0.0000', updated_at: createdAt, is_owner: true, created_at: createdAt, owner_id: userId }
      projectStore.unshift(project)
      memberStore[project.id] = [{ user_id: userId, display_name: 'You', email: '', role: 'owner', joined_at: createdAt }]
      const prompts: Prompt[] = [
        { id: `${project.id}-assistant`, project_id: project.id, key: 'customer-assistant', name: 'Customer assistant', description: 'Answers common customer questions with a clear, helpful tone.', latest_version_number: 2, active_environment: 'staging', created_at: createdAt, updated_at: createdAt },
        { id: `${project.id}-summary`, project_id: project.id, key: 'conversation-summary', name: 'Conversation summary', description: 'Summarizes key decisions and next steps from a conversation.', latest_version_number: 1, active_environment: 'draft', created_at: createdAt, updated_at: createdAt },
      ]
      promptStore.unshift(...prompts)
      versionStore[prompts[0].id] = [
        { id: `${prompts[0].id}-v2`, prompt_id: prompts[0].id, version_number: 2, parent_version_id: `${prompts[0].id}-v1`, template: 'You are a helpful customer assistant. Answer the customer clearly and include the next best step.\n\nCustomer message:\n{{customer_message}}', variables: [{ name: 'customer_message', description: 'The customer’s question.', required: true }], model_config: { provider: 'mock', model: 'deterministic-v1', temperature: 0.3, max_output_tokens: 400 }, commit_message: 'Clarify next steps', created_by: userId, created_by_name: 'You', created_at: createdAt },
        { id: `${prompts[0].id}-v1`, prompt_id: prompts[0].id, version_number: 1, parent_version_id: null, template: 'Answer this customer question:\n{{customer_message}}', variables: [{ name: 'customer_message', required: true }], model_config: { provider: 'mock', model: 'deterministic-v1', temperature: 0.3, max_output_tokens: 400 }, commit_message: 'Initial version', created_by: userId, created_by_name: 'You', created_at: createdAt },
      ]
      versionStore[prompts[1].id] = [{ id: `${prompts[1].id}-v1`, prompt_id: prompts[1].id, version_number: 1, parent_version_id: null, template: 'Summarize the conversation below as decisions, open questions, and next steps.\n\nConversation:\n{{conversation}}', variables: [{ name: 'conversation', description: 'The conversation to summarize.', required: true }], model_config: { provider: 'mock', model: 'deterministic-v1', temperature: 0.2, max_output_tokens: 350 }, commit_message: 'Initial version', created_by: userId, created_by_name: 'You', created_at: createdAt }]
      notifyMutation()
      return project
    }
    const result = await apiClient.request<BackendProject>('/projects', { method: 'POST', body: request })
    const project = adaptProject(result, userId)
    replaceProject(project)
    notifyMutation()
    return project
  },
  async updateProject(projectId: string, request: UpdateProjectRequest, userId: string) {
    if (useDemoData) {
      const current = projectFor(projectId)
      if (!current) throw new Error('Project not found.')
      const project = { ...current, ...request, updated_at: new Date().toISOString() }
      replaceProject(project)
      notifyMutation()
      return project
    }
    const result = await apiClient.request<BackendProject>(`/projects/${projectId}`, { method: 'PATCH', body: request })
    const project = adaptProject(result, userId)
    replaceProject(project)
    notifyMutation()
    return project
  },
  async loadMembers(projectId: string) {
    if (useDemoData) return memberStore[projectId] ?? []
    const generation = (memberGenerations.get(projectId) ?? 0) + 1
    memberGenerations.set(projectId, generation)
    const members = (await loadAllPages<BackendMember>(`/projects/${projectId}/members`)).map(adaptMember)
    if (memberGenerations.get(projectId) !== generation) return memberStore[projectId] ?? []
    memberStore[projectId] = members
    const project = projectFor(projectId)
    if (project) project.member_count = members.length
    notify()
    return members
  },
  async addMember(projectId: string, request: AddProjectMemberRequest) {
    memberGenerations.set(projectId, (memberGenerations.get(projectId) ?? 0) + 1)
    const invitation = await apiClient.request<import('../../types/projects').ProjectInvitation>(`/projects/${projectId}/members`, { method: 'POST', body: request })
    // Pending invitations do not alter the member store or member count.
    memberGenerations.set(projectId, (memberGenerations.get(projectId) ?? 0) + 1)
    return invitation
  },
  async removeMember(projectId: string, userId: string) {
    memberGenerations.set(projectId, (memberGenerations.get(projectId) ?? 0) + 1)
    await apiClient.request<void>(`/projects/${projectId}/members/${userId}`, { method: 'DELETE' })
    memberGenerations.set(projectId, (memberGenerations.get(projectId) ?? 0) + 1)
    memberStore[projectId] = (memberStore[projectId] ?? []).filter((member) => member.user_id !== userId)
    const project = projectFor(projectId)
    if (project) project.member_count = memberStore[projectId].length
    notifyMutation()
    refreshLiveData()
  },
  async createPrompt(projectId: string, request: CreatePromptRequest) {
    const result = await apiClient.request<BackendPromptDetail>(`/projects/${projectId}/prompts`, {
      method: 'POST',
      body: {
        key: request.key,
        name: request.name,
        description: request.description,
        template_body: request.template,
        model_config: request.model_config,
        commit_message: request.commit_message,
      },
    })
    const prompt = adaptPromptDetail(result)
    replacePrompt(prompt)
    activeVersionsStore[prompt.id] = result.active_versions
    versionStore[prompt.id] = [adaptVersion(result.latest_version)]
    const project = projectFor(projectId)
    if (project) project.prompt_count += 1
    notifyMutation()
    refreshLiveData()
    return prompt
  },
  async createVersion(promptId: string, request: CreateVersionRequest) {
    const result = await apiClient.request<BackendVersion>(`/prompts/${promptId}/versions`, {
      method: 'POST',
      body: {
        parent_version_id: request.parent_version_id,
        template_body: request.template,
        model_config: request.model_config,
        commit_message: request.commit_message,
      },
    })
    const version = adaptVersion(result)
    versionStore[promptId] = [version, ...(versionStore[promptId] ?? []).filter((item) => item.id !== version.id)].sort((left, right) => right.version_number - left.version_number)
    const prompt = promptFor(promptId)
    if (prompt && version.version_number >= prompt.latest_version_number) {
      prompt.latest_version_number = version.version_number
      prompt.updated_at = version.created_at
    }
    notifyMutation()
    return version
  },
}
