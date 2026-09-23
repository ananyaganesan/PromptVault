import type { Id, IsoDateString, Money, PageQuery } from './api'

export interface ProjectSummary {
  id: Id
  key: string
  name: string
  description: string | null
  prompt_count: number
  member_count: number
  monthly_spend: Money
  updated_at: IsoDateString
  is_owner: boolean
}

export interface Project extends ProjectSummary {
  created_at: IsoDateString
  owner_id: Id
}

export interface ProjectMember {
  user_id: Id
  display_name: string
  email: string
  role: 'owner' | 'member'
  joined_at: IsoDateString
}

export interface CreateProjectRequest {
  name: string
  key: string
  description?: string
}

export interface UpdateProjectRequest {
  name?: string
  description?: string | null
}

export interface AddProjectMemberRequest {
  email: string
}

export interface ProjectListQuery extends PageQuery {
  search?: string
}
