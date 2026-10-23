import { useCallback, useEffect, useState } from 'react'
import { apiClient } from '../../lib/api/client'
import { useDemoData } from '../../lib/runtime'

export interface ProviderModel {
  id: string
  label: string
  max_output_tokens: number
  max_input_characters: number
  free_access: boolean
  available: boolean
  unavailable_reason: string | null
}
export interface ProviderInfo {
  provider: 'gemini'
  credential_available: boolean
  models: ProviderModel[]
  quota_note: string
}
export interface ProviderDiscovery {
  items: ProviderInfo[]
  max_concurrent_runs_per_user: number
  timeout_seconds: number
  credential_ownership: string
}

export function useProviderModels() {
  const [data, setData] = useState<ProviderDiscovery | null>(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const refresh = useCallback(() => { setData(null); setError(''); setRevision((value) => value + 1) }, [])
  useEffect(() => {
    if (useDemoData) return
    const controller = new AbortController()
    apiClient.request<ProviderDiscovery>('/providers/models', { signal: controller.signal })
      .then((result) => { if (!controller.signal.aborted) { setData(result); setError('') } })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setData(null)
          setError(cause instanceof Error ? cause.message : 'Could not load provider models.')
        }
      })
    return () => controller.abort()
  }, [revision])
  return { data, error, refresh }
}
