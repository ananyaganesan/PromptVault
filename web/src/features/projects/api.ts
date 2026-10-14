import { apiClient } from '../../lib/api/client'
import type { Id, Page } from '../../types/api'
import type { AddProjectMemberRequest, CreateProjectRequest, Project, ProjectListQuery, ProjectMember, ProjectInvitation, ProjectSummary, UpdateProjectRequest } from '../../types/projects'

export const projectsApi = {
  list: (query: ProjectListQuery = {}, signal?: AbortSignal) => apiClient.request<Page<ProjectSummary>>('/projects', { query: { ...query }, signal }),
  create: (request: CreateProjectRequest) => apiClient.request<Project>('/projects', { method: 'POST', body: request }),
  get: (projectId: Id, signal?: AbortSignal) => apiClient.request<Project>(`/projects/${projectId}`, { signal }),
  update: (projectId: Id, request: UpdateProjectRequest) => apiClient.request<Project>(`/projects/${projectId}`, { method: 'PATCH', body: request }),
  delete: (projectId: Id) => apiClient.request<void>(`/projects/${projectId}`, { method: 'DELETE' }),
  listMembers: (projectId: Id, signal?: AbortSignal) => apiClient.request<ProjectMember[]>(`/projects/${projectId}/members`, { signal }),
  addMember: (projectId: Id, request: AddProjectMemberRequest) => apiClient.request<ProjectInvitation>(`/projects/${projectId}/members`, { method: 'POST', body: request }),
  listInvitations: (projectId: Id, signal?: AbortSignal) => apiClient.request<ProjectInvitation[]>(`/projects/${projectId}/invitations`, { signal }),
  cancelInvitation: (projectId: Id, invitationId: Id) => apiClient.request<void>(`/projects/${projectId}/invitations/${invitationId}`, { method: 'DELETE' }),
  acceptInvitation: (token: string) => apiClient.request<{ id: string }>('/project-invitations/accept', { method: 'POST', body: { token } }),
  removeMember: (projectId: Id, userId: Id) => apiClient.request<void>(`/projects/${projectId}/members/${userId}`, { method: 'DELETE' }),
}
