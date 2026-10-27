import { apiClient } from '../../lib/api/client'
import type { BackendVersion } from '../projects/workspace-data'

export const metricNames = ['correctness', 'relevance', 'instruction_following', 'completeness', 'clarity'] as const
export type Metric = typeof metricNames[number]
export type Preset = 'accurate_answers' | 'customer_support' | 'summarization' | 'structured_json'
export type Weights = Record<Metric, number>
export interface TestCase { name: string; variables: Record<string, string>; reference: string }
export interface Requirements { valid_json: boolean; required_fields: string[]; max_words: number | null }
export interface Setup { version_ids: string[]; goal: string; preset: Preset; cases: TestCase[]; weights: Weights; requirements: Requirements }
export interface SuggestedSetup { cases: TestCase[]; weights: Weights; requirements: Requirements; notes: string }
export interface MetricScore { score: number; reason: string; evidence: string }
export interface CaseResult {
  version_id: string; case_index: number; run_id: string | null; output: string;
  checks: Array<{ name: string; passed: boolean; detail: string }>;
  scores: Partial<Record<Metric, MetricScore>>; weighted_score: number | null;
  summary: string; error: string | null; prompt_tokens: number; completion_tokens: number; latency_ms: number;
}
export interface Ranking { version_id: string; score: number | null; eligible: boolean; passed_cases: number; total_cases: number; reason: string }
export interface Evaluation {
  id: string; prompt_id: string; created_by: string; configuration: Setup; version_snapshots: BackendVersion[];
  status: 'queued' | 'running' | 'completed' | 'failed' | 'interrupted';
  results: CaseResult[]; ranking: Ranking[]; recommendation: string; winner_version_id: string | null;
  error: string | null; created_at: string; updated_at: string; usage: Record<string, number>;
}
export interface HistoryItem { id: string; status: Evaluation['status']; created_at: string; recommendation: string; winner_version_id: string | null; error: string | null; completed_cases: number; total_cases: number }
export interface Improvement { template: string; explanation: string }
const path = (id: string) => `/prompts/${id}`
export const evaluationApi = {
  setup: (id: string, signal?: AbortSignal) => apiClient.request<{ configuration: Setup | null }>(`${path(id)}/evaluation-setup`, { signal }),
  saveSetup: (id: string, body: Setup) => apiClient.request(`${path(id)}/evaluation-setup`, { method: 'PUT', body }),
  suggest: (id: string, body: Pick<Setup, 'version_ids' | 'goal' | 'preset'>) => apiClient.request<SuggestedSetup>(`${path(id)}/evaluation-suggestions`, { method: 'POST', body }),
  start: (promptId: string, id: string, configuration: Setup) => apiClient.request<Evaluation>(`${path(promptId)}/evaluations`, { method: 'POST', body: { id, configuration } }),
  get: (promptId: string, id: string, signal?: AbortSignal) => apiClient.request<Evaluation>(`${path(promptId)}/evaluations/${id}`, { signal }),
  history: (id: string, signal?: AbortSignal) => apiClient.request<HistoryItem[]>(`${path(id)}/evaluations`, { signal }),
  improve: (promptId: string, id: string, version_id: string) => apiClient.request<Improvement>(`${path(promptId)}/evaluations/${id}/improvement`, { method: 'POST', body: { version_id } }),
}
export const metricLabel = (metric: string) => metric.replace(/_/g, ' ').replace(/^./, (s) => s.toUpperCase())
export const metricDefinitions: Record<Metric, string> = {
  correctness: 'Matches the trusted answer you provide, without making up facts.',
  relevance: 'Directly addresses the question and desired outcome.',
  instruction_following: 'Follows your instructions, including tone and answer format.',
  completeness: 'Includes essential information and next steps.',
  clarity: 'Easy to understand, well organized, and concise.',
}
export const defaults: Weights = { correctness: 30, relevance: 25, instruction_following: 20, completeness: 15, clarity: 10 }
export const presets: Record<Preset, { label: string; goal: string; weights: Weights }> = {
  accurate_answers: { label: 'Accurate answers', goal: 'Answer the question accurately using the supplied information. Be relevant, complete, and clear.', weights: defaults },
  customer_support: { label: 'Customer support', goal: 'Resolve the customer’s issue with a helpful, empathetic answer and a practical next step. Follow the supplied policy.', weights: { correctness: 25, relevance: 25, instruction_following: 20, completeness: 15, clarity: 15 } },
  summarization: { label: 'Summarization', goal: 'Summarize the source faithfully, retaining the key facts without adding unsupported details.', weights: { correctness: 30, relevance: 15, instruction_following: 15, completeness: 25, clarity: 15 } },
  structured_json: { label: 'Organized information', goal: 'Present the requested information in a consistent format, with accurate details and no extra commentary.', weights: { correctness: 25, relevance: 15, instruction_following: 40, completeness: 15, clarity: 5 } },
}
