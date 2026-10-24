import { ArrowLeft } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { promptFor, promptStore, versionsFor } from '../../features/projects/workspace-data'

const sidebarDestinations = new Set([
  '/dashboard',
  '/projects',
  '/playground',
  '/deployments',
  '/api-tokens',
  '/profile',
  '/admin/approvals',
  '/admin/rollback',
  '/admin/users',
  '/admin/provider-keys',
  '/admin/audit',
])

export function ProjectBackButton() {
  const { pathname, search } = useLocation()
  const navigate = useNavigate()
  if (sidebarDestinations.has(pathname)) return null

  const isWorkspacePage = /^\/(projects|prompts|versions|playground|deployments|api-tokens|profile|admin)(\/|$)/.test(pathname)
  if (!isWorkspacePage) return null

  function fallbackParent() {
    const [, section, id, view] = pathname.split('/')

    if (section === 'projects') return id ? '/projects' : '/dashboard'

    if (section === 'prompts') {
      if (!id) return '/projects'
      const projectId = id === 'new'
        ? new URLSearchParams(search).get('project')
        : promptFor(id)?.project_id
      return projectId ? `/projects/${projectId}` : '/prompts'
    }

    if (section === 'versions') {
      if (view) return `/versions/${id}`
      const prompt = promptStore.find((item) => versionsFor(item.id).some((version) => version.id === id))
      return prompt ? `/prompts/${prompt.id}` : '/prompts'
    }

    if (section === 'deployments') return id ? '/deployments' : '/dashboard'

    if (section === 'admin') {
      if (id === 'approvals' && view) return '/admin/approvals'
      return '/dashboard'
    }

    return '/dashboard'
  }

  function goBack() {
    if (window.history.state?.idx > 0) {
      navigate(-1)
      return
    }
    navigate(fallbackParent())
  }

  return <button type="button" className="project-back-button" aria-label="Go back" title="Go back" onClick={goBack}>
    <ArrowLeft size={12} strokeWidth={1.75} aria-hidden="true" />
  </button>
}
