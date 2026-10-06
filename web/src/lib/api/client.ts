import type { ApiErrorEnvelope, QueryParams } from '../../types/api'

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL ?? import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const defaultBaseUrl = configuredBaseUrl.endsWith('/api/v1')
  ? configuredBaseUrl
  : `${configuredBaseUrl.replace(/\/$/, '')}/api/v1`

export class ApiClientError extends Error {
  readonly code: ApiErrorEnvelope['code']
  readonly fieldErrors?: ApiErrorEnvelope['field_errors']
  readonly requestId?: string
  readonly status: number

  constructor(status: number, response: ApiErrorEnvelope) {
    super(response.message)
    this.name = 'ApiClientError'
    this.status = status
    this.code = response.code
    this.fieldErrors = response.field_errors
    this.requestId = response.request_id
  }
}

export interface RequestOptions {
  method?: 'DELETE' | 'GET' | 'PATCH' | 'POST' | 'PUT'
  body?: unknown
  query?: QueryParams
  signal?: AbortSignal
  auth?: boolean
}

export interface ApiClientOptions {
  baseUrl?: string
  getAccessToken?: () => string | null
  fetcher?: typeof fetch
  onUnauthorized?: () => void
}

function toUrl(path: string, baseUrl: string, query?: QueryParams) {
  const url = new URL(path.replace(/^\//, ''), `${baseUrl.replace(/\/$/, '')}/`)
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value == null) continue
    url.searchParams.set(key, String(value))
  }
  return url.toString()
}

async function readJson(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') ?? ''
  return contentType.includes('application/json') ? response.json() : undefined
}

function fallbackError(status: number): ApiErrorEnvelope {
  return { code: 'internal_error', message: `Request failed with status ${status}` }
}

export function createApiClient({ baseUrl = defaultBaseUrl, getAccessToken = () => accessToken, fetcher, onUnauthorized = notifyUnauthorized }: ApiClientOptions = {}) {
  return {
    async request<T>(path: string, { method = 'GET', body, query, signal, auth = true }: RequestOptions = {}): Promise<T> {
      const token = auth ? getAccessToken() : null
      const response = await (fetcher ?? fetch)(toUrl(path, baseUrl, query), {
        method,
        signal,
        headers: {
          Accept: 'application/json',
          ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
      const payload = await readJson(response)
      if (response.status === 401 && auth) onUnauthorized()
      if (!response.ok) throw new ApiClientError(response.status, isErrorEnvelope(payload) ? payload : fallbackError(response.status))
      return payload as T
    },
  }
}

function isErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  return value !== null && typeof value === 'object' && 'code' in value && 'message' in value
}

let accessToken: string | null = null
const unauthorizedListeners = new Set<() => void>()
function notifyUnauthorized() { unauthorizedListeners.forEach((listener) => listener()) }

export function setAccessToken(token: string | null) { accessToken = token }
export function clearAccessToken() { accessToken = null }
export function subscribeUnauthorized(listener: () => void) {
  unauthorizedListeners.add(listener)
  return () => { unauthorizedListeners.delete(listener) }
}
export const apiClient = createApiClient()
