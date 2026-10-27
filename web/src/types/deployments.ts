import type { ReleaseValidation } from '../features/deployments/release-validation-api'
import type { Id, IsoDateString, PageQuery } from './api'

export type DeploymentEnvironment = 'development' | 'staging' | 'production'
export type DeploymentStatus = 'active' | 'pending_approval' | 'rejected' | 'cancelled' | 'superseded' | 'rolled_back'

export interface DeploymentTimelineEvent {
  id: Id
  version_id: Id
  version_number: number
  status: DeploymentStatus
  requested_at: IsoDateString
  reviewed_at: IsoDateString | null
  activated_at: IsoDateString | null
}

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
  requested_at?: IsoDateString
  activated_at?: IsoDateString | null
  rollback_of_id?: Id | null
  rollback_reason?: string | null
  timeline?: DeploymentTimelineEvent[]
  validation?: ReleaseValidation | null
  validation_id?: Id | null
}

export interface CreateDeploymentRequest {
  validation_id?: Id
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
  token_prefix: string
  created_at: IsoDateString
  expires_at: IsoDateString | null
  revoked_at: IsoDateString | null
}

export interface CreateApiTokenRequest {
  name: string
  project_id: Id
  expires_at?: IsoDateString
}

export interface CreatedApiToken extends ApiTokenMetadata {
  token: string
}
