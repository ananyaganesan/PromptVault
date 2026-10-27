import { apiClient } from '../../lib/api/client'
import type { Evaluation, Improvement, Setup } from '../evaluations/evaluation-api'
import type { BackendDeploymentEnvironment } from './api'

export type ReleaseSuite = Pick<Setup, 'goal' | 'cases' | 'requirements' | 'weights'>
export interface ReleaseValidation {
  id: string
  version_id: string
  environment: BackendDeploymentEnvironment
  created_by: string
  base_deployment_id: string | null
  created_at: string
  status: 'queued' | 'running' | 'passed' | 'blocked' | 'stale'
  summary: string
  minimum_score: number
  checks: Array<{ name: string; passed: boolean; detail: string }>
  configuration: Setup | null
  evaluation: Evaluation | null
}
export const releaseValidationApi = {
  start: (body: { id: string; version_id: string; environment: BackendDeploymentEnvironment; suite?: ReleaseSuite }) => apiClient.request<ReleaseValidation>('/deployments/validations', { method: 'POST', body }),
  get: (id: string, signal?: AbortSignal) => apiClient.request<ReleaseValidation>(`/deployments/validations/${id}`, { signal }),
  fix: (id: string) => apiClient.request<Improvement>(`/deployments/validations/${id}/suggest-fix`, { method: 'POST' }),
}
