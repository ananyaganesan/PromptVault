import type { Id, IsoDateString, PageQuery } from './api'

export type PromptEnvironment = 'development' | 'staging' | 'production' | 'draft'

export interface PromptVariable {
  name: string
  description?: string
  required: boolean
  default_value?: string
}

export interface ModelConfig {
  provider: string
  model: string
  temperature?: number
  max_output_tokens?: number
}

export interface PromptSummary {
  id: Id
  project_id: Id
  key: string
  name: string
  description: string | null
  latest_version_number: number
  active_environment: PromptEnvironment
  updated_at: IsoDateString
}

export interface Prompt extends PromptSummary {
  created_at: IsoDateString
}

export interface CreatePromptRequest {
  key: string
  name: string
  description?: string
  template: string
  variables: PromptVariable[]
  model_config: ModelConfig
  commit_message: string
}

export interface PromptListQuery extends PageQuery {
  search?: string
  project_id?: Id
  environment?: PromptEnvironment
}
