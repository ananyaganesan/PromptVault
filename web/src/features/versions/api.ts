import { apiClient } from '../../lib/api/client'
import type { Id } from '../../types/api'
import type { BackendVersion } from '../projects/workspace-data'

export interface BackendVersionDiff {
  from_version_id: Id
  to_version_id: Id
  template_body: { changed: boolean; before: string; after: string }
  variables: { added: string[]; removed: string[] }
  model_config: {
    changed_fields: string[]
    before: BackendVersion['model_config']
    after: BackendVersion['model_config']
  }
}

export interface BackendVersionLineage {
  items: BackendVersion[]
  cycle_detected: boolean
}

export const versionsApi = {
  get: (versionId: Id, signal?: AbortSignal) => apiClient.request<BackendVersion>(`/versions/${versionId}`, { signal }),
  diff: (versionId: Id, against: Id, signal?: AbortSignal) => apiClient.request<BackendVersionDiff>(`/versions/${versionId}/diff`, { query: { against }, signal }),
  lineage: (versionId: Id, signal?: AbortSignal) => apiClient.request<BackendVersionLineage>(`/versions/${versionId}/lineage`, { signal }),
}
