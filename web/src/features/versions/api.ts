import { apiClient } from '../../lib/api/client'
import type { Id } from '../../types/api'
import type { PromptVersion, VersionDiff, VersionLineage } from '../../types/versions'

export const versionsApi = {
  get: (versionId: Id, signal?: AbortSignal) => apiClient.request<PromptVersion>(`/versions/${versionId}`, { signal }),
  diff: (versionId: Id, compareTo?: Id, signal?: AbortSignal) => apiClient.request<VersionDiff>(`/versions/${versionId}/diff`, { query: { compare_to: compareTo }, signal }),
  lineage: (versionId: Id, signal?: AbortSignal) => apiClient.request<VersionLineage>(`/versions/${versionId}/lineage`, { signal }),
}
