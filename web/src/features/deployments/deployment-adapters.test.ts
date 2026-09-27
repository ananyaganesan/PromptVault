import { describe, expect, it } from 'vitest'
import { adaptBackendDeployment, adaptBackendToken } from './deployment-service'

describe('deployment API adapters', () => {
  it('maps backend deployment vocabulary and actor objects to the existing view model', () => {
    expect(adaptBackendDeployment({
      id: 'deployment-id',
      project_id: 'project-id',
      prompt_id: 'prompt-id',
      prompt_key: 'support-reply',
      version_id: 'version-id',
      version_number: 3,
      environment: 'prod',
      status: 'pending',
      request_note: 'Ready for review',
      review_note: null,
      rollback_reason: null,
      rollback_of_id: null,
      requested_by: { id: 'user-id', display_name: 'Demo User' },
      reviewed_by: null,
      requested_at: '2026-09-27T00:00:00Z',
      reviewed_at: null,
      activated_at: null,
    })).toMatchObject({
      environment: 'production',
      status: 'pending_approval',
      note: 'Ready for review',
      requested_by: 'user-id',
      requested_by_name: 'Demo User',
      created_at: '2026-09-27T00:00:00Z',
    })
  })

  it('adds safe project display data without inventing token usage metadata', () => {
    expect(adaptBackendToken({
      id: 'token-id',
      project_id: 'project-id',
      name: 'Production consumer',
      token_prefix: 'pv_1234',
      created_by: 'user-id',
      created_at: '2026-09-27T00:00:00Z',
      expires_at: null,
      revoked_at: null,
    }, 'Checkout Assistant')).toEqual(expect.objectContaining({
      project_name: 'Checkout Assistant',
      last_used_at: null,
      revoked_at: null,
    }))
  })
})
