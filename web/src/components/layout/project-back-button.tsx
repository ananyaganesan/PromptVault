import { ArrowLeft } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { promptFor, promptStore, versionsFor } from '../../features/projects/workspace-data'

export function ProjectBackButton() {
  const { pathname, search } = useLocation()
  const navigate = useNavigate()
  if (!/^\/(projects|prompts|versions)(\/|$)/.test(pathname)) return null

  function goBack() {
    if (window.history.state?.idx > 0) {
      navigate(-1)
      return
    }

    const [, section, id, view] = pathname.split('/')
    let parent = '/projects'
    if (section === 'projects' && !id) parent = '/dashboard'
    if (section === 'prompts') {
      const projectId = id === 'new' ? new URLSearchParams(search).get('project') : promptFor(id)?.project_id
      if (projectId) parent = `/projects/${projectId}`
    }
    if (section === 'versions') {
      const prompt = promptStore.find((item) => versionsFor(item.id).some((version) => version.id === id))
      if (view) parent = `/versions/${id}`
      else if (prompt) parent = `/prompts/${prompt.id}`
    }
    navigate(parent)
  }

  return <button type="button" className="project-back-button" aria-label="Go back" title="Go back" onClick={goBack}>
    <ArrowLeft size={12} strokeWidth={1.75} aria-hidden="true" />
  </button>
}
