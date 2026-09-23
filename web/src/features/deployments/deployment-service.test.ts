import { describe, expect, it } from 'vitest'
import { demoUsers } from '../../mocks/users'
import { deploymentService, tokenService } from './deployment-service'

const member = demoUsers[0]
const admin = demoUsers[1]

describe('deployment workflow', () => {
  it('queues production requests and limits review to Super Admins', async () => {
    const request = await deploymentService.create({ version_id: 'checkout-v3', environment: 'production', note: 'Ready for review' }, member)
    expect(request.status).toBe('pending_approval')
    expect((await deploymentService.pending(admin)).some((item) => item.id === request.id)).toBe(true)
    await expect(deploymentService.review(request.id, 'approve', {}, member)).rejects.toThrow('Super Admin')
    const approved = await deploymentService.review(request.id, 'approve', { note: 'Validated' }, admin)
    expect(approved.status).toBe('active')
    await expect(deploymentService.review(request.id, 'approve', {}, admin)).rejects.toThrow('already been reviewed')
  })

  it('allows only the requester to cancel a pending request', async () => {
    const request = await deploymentService.create({ version_id: 'checkout-v3', environment: 'production' }, member)
    await expect(deploymentService.cancel(request.id, admin)).rejects.toThrow('Only the requester')
    expect((await deploymentService.cancel(request.id, member)).status).toBe('cancelled')
  })

  it('preserves history when rolling an active deployment back', async () => {
    const active = await deploymentService.create({ version_id: 'checkout-v3', environment: 'staging' }, member)
    const rollback = await deploymentService.rollback(active.id, 'checkout-v2', 'Restore stable tone', admin)
    expect(rollback.version_number).toBe(2)
    expect(rollback.status).toBe('active')
    expect((await deploymentService.get(active.id))?.status).toBe('superseded')
    await expect(deploymentService.rollback(rollback.id, 'checkout-v3', '', admin)).rejects.toThrow('reason is required')
  })
})

describe('API token lifecycle', () => {
  it('reveals the secret on issue only, then lists metadata and revokes', async () => {
    const issued = await tokenService.issue({ name: 'Runtime consumer', project_id: 'checkout' }, member)
    expect(issued.token).toMatch(/^pv_[a-f0-9]+$/)
    const listed = (await tokenService.list()).find((item) => item.id === issued.id)
    expect(listed).toBeDefined()
    expect(listed).not.toHaveProperty('token')
    await tokenService.revoke(issued.id, member)
    expect((await tokenService.list()).find((item) => item.id === issued.id)?.revoked_at).not.toBeNull()
  })
})
