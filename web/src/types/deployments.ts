import type { Id, IsoDateString, PageQuery } from './api'

export type DeploymentEnvironment = 'development' | 'staging' | 'production'
export type DeploymentStatus = 'active' | 'pending_approval' | 'approved' | 'rejected' | 'cancelled' | 'superseded'

export interface Deployment {
  id: Id
  project_id: Id
  project_name: string
  prompt_id: Id
  prompt_key: string
  version_id: Id
  version_number: number
  environment: DeploymentEnvironment
  status: DeploymentStatus
  note: string | null
  requested_by: Id
  requested_by_name: string
  reviewed_by: Id | null
  reviewed_at: IsoDateString | null
  review_note: string | null
  created_at: IsoDateString
}

export interface CreateDeploymentRequest {
  version_id: Id
  environment: DeploymentEnvironment
  note?: string
}

export interface ReviewDeploymentRequest {
  note?: string
}

export interface DeploymentListQuery extends PageQuery {
  project_id?: Id
  environment?: DeploymentEnvironment
  status?: DeploymentStatus
}

export interface ApiTokenMetadata {
  id: Id
  name: string
  project_id: Id
  project_name: string
  created_at: IsoDateString
  last_used_at: IsoDateString | null
  revoked_at: IsoDateString | null
}

export interface CreateApiTokenRequest {
  name: string
  project_id: Id
}

export interface CreatedApiToken extends ApiTokenMetadata {
  token: string
}
