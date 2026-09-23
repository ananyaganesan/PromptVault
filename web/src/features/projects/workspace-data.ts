import type { Project, ProjectMember } from '../../types/projects'
import type { Prompt, PromptVariable } from '../../types/prompts'
import type { PromptVersion } from '../../types/versions'

export const projectStore: Project[] = [
  { id: 'checkout', key: 'checkout-assistant', name: 'Checkout Assistant', description: 'Prompts for the checkout support experience.', prompt_count: 3, member_count: 5, monthly_spend: '$0.0140', updated_at: '2025-08-28T10:30:00Z', is_owner: true, created_at: '2025-08-01T09:00:00Z', owner_id: 'usr_demo_admin' },
  { id: 'growth', key: 'growth-tools', name: 'Growth Tools', description: 'Experiment prompts for the growth team.', prompt_count: 0, member_count: 1, monthly_spend: '$0.0000', updated_at: '2025-08-27T11:00:00Z', is_owner: true, created_at: '2025-07-10T09:00:00Z', owner_id: 'usr_demo_admin' },
  { id: 'support', key: 'internal-support', name: 'Internal Support', description: 'Internal support helpers and triage.', prompt_count: 0, member_count: 1, monthly_spend: '$0.0000', updated_at: '2025-08-24T11:00:00Z', is_owner: false, created_at: '2025-07-01T09:00:00Z', owner_id: 'sam' },
]

export const memberStore: Record<string, ProjectMember[]> = {
  checkout: [
    { user_id: 'usr_demo_admin', display_name: 'Alex Morgan', email: 'admin@promptvault.dev', role: 'owner', joined_at: '2025-08-01T09:00:00Z' },
    { user_id: 'usr_demo_user', display_name: 'Jamie Chen', email: 'user@promptvault.dev', role: 'member', joined_at: '2025-08-01T10:00:00Z' },
    { user_id: 'ananya', display_name: 'Ananya Ganesan', email: 'ananya@promptvault.dev', role: 'member', joined_at: '2025-08-02T09:00:00Z' },
    { user_id: 'jobin', display_name: 'Jobin Thomas', email: 'jobin@promptvault.dev', role: 'member', joined_at: '2025-08-04T09:00:00Z' },
    { user_id: 'sam', display_name: 'Sam Rivera', email: 'sam@promptvault.dev', role: 'member', joined_at: '2025-08-05T09:00:00Z' },
  ],
  growth: [{ user_id: 'usr_demo_admin', display_name: 'Alex Morgan', email: 'admin@promptvault.dev', role: 'owner', joined_at: '2025-07-10T09:00:00Z' }],
  support: [{ user_id: 'sam', display_name: 'Sam Rivera', email: 'sam@promptvault.dev', role: 'owner', joined_at: '2025-07-01T09:00:00Z' }],
}

const checkoutVariables: PromptVariable[] = [
  { name: 'customer_message', description: 'The customer’s checkout question.', required: true },
  { name: 'order_context', description: 'Relevant order status and payment context.', required: false, default_value: 'No order context provided.' },
]

export const promptStore: Prompt[] = [
  { id: 'checkout-reply', project_id: 'checkout', key: 'checkout-reply', name: 'Customer checkout reply', description: 'Answer customer questions about checkout with a clear, friendly tone.', latest_version_number: 3, active_environment: 'staging', updated_at: '2025-08-28T10:30:00Z', created_at: '2025-08-18T09:00:00Z' },
  { id: 'order-status', project_id: 'checkout', key: 'order-status', name: 'Order status assistant', description: 'Explain order status in helpful, plain language.', latest_version_number: 2, active_environment: 'production', updated_at: '2025-08-27T10:00:00Z', created_at: '2025-08-14T09:00:00Z' },
  { id: 'refund-policy', project_id: 'checkout', key: 'refund-policy', name: 'Refund policy response', description: 'Give a concise response about refund eligibility.', latest_version_number: 1, active_environment: 'draft', updated_at: '2025-08-23T10:00:00Z', created_at: '2025-08-23T09:00:00Z' },
]

export const versionStore: Record<string, PromptVersion[]> = {
  'checkout-reply': [
    { id: 'checkout-v3', prompt_id: 'checkout-reply', version_number: 3, parent_version_id: 'checkout-v2', template: 'You are a helpful checkout support assistant.\n\nCustomer message:\n{{customer_message}}\n\nOrder context:\n{{order_context}}\n\nRespond with a concise, reassuring answer.', variables: checkoutVariables, model_config: { provider: 'openai', model: 'gpt-4o-mini', temperature: 0.3, max_output_tokens: 300 }, commit_message: 'Add order context variable', created_by: 'alex', created_by_name: 'Alex Morgan', created_at: '2025-08-28T10:30:00Z' },
    { id: 'checkout-v2', prompt_id: 'checkout-reply', version_number: 2, parent_version_id: 'checkout-v1', template: 'You are a helpful checkout support assistant.\n\nCustomer message:\n{{customer_message}}\n\nRespond with a clear, reassuring answer.', variables: [checkoutVariables[0]], model_config: { provider: 'openai', model: 'gpt-4o-mini', temperature: 0.3, max_output_tokens: 300 }, commit_message: 'Improve tone instructions', created_by: 'ananya', created_by_name: 'Ananya Ganesan', created_at: '2025-08-24T10:30:00Z' },
    { id: 'checkout-v1', prompt_id: 'checkout-reply', version_number: 1, parent_version_id: null, template: 'Answer this customer checkout question:\n{{customer_message}}', variables: [checkoutVariables[0]], model_config: { provider: 'openai', model: 'gpt-4o-mini', temperature: 0.5, max_output_tokens: 200 }, commit_message: 'Initial prompt version', created_by: 'alex', created_by_name: 'Alex Morgan', created_at: '2025-08-18T09:00:00Z' },
  ],
}

export function displayDate(value: string) { return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value)) }
export function projectFor(id?: string) { return projectStore.find((project) => project.id === id) }
export function promptFor(id?: string) { return promptStore.find((prompt) => prompt.id === id) }
export function versionsFor(promptId: string) { return versionStore[promptId] ?? [] }
