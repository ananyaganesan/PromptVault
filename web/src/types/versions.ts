import type { Id, IsoDateString } from './api'
import type { ModelConfig, PromptVariable } from './prompts'

export interface PromptVersion {
  id: Id
  prompt_id: Id
  version_number: number
  parent_version_id: Id | null
  template: string
  variables: PromptVariable[]
  model_config: ModelConfig
  commit_message: string
  created_by: Id
  created_by_name: string
  created_at: IsoDateString
}

export interface CreateVersionRequest {
  template: string
  variables: PromptVariable[]
  model_config: ModelConfig
  commit_message: string
  parent_version_id?: Id
}

export interface VersionDiff {
  base_version: PromptVersion
  compare_version: PromptVersion
  template_diff: string
  variables_changed: boolean
  model_config_changed: boolean
}

export interface VersionLineage {
  version: PromptVersion
  ancestors: PromptVersion[]
}
