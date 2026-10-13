import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

export function invitationLink(email: string, projectName?: string): string {
  const mailbox = process.env.E2E_MAILBOX_DIR
  if (!mailbox) throw new Error('Invitation acceptance requires E2E_MAILBOX_DIR and local SMTP capture.')
  const messages = readdirSync(mailbox).filter((name) => name.endsWith('.json'))
    .map((name) => JSON.parse(readFileSync(join(mailbox, name), 'utf8')) as { recipient: string; text: string })
  const message = messages.find((item) => item.recipient === email && item.text.includes('/project-invitations#token=') && (!projectName || item.text.includes(projectName)))
  const link = message?.text.match(/https?:\/\/[^\s]+\/project-invitations#token=[\w-]+/)?.[0]
  if (!link) throw new Error('Invitation email was not captured.')
  return link
}
