import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { PageHeader } from '../../components/layout/page-header'
import { Button, Stat, Status } from '../../components/ui/prototype'
import { promptStore, versionStore } from '../projects/workspace-data'
import { runService } from '../runs/run-service'
import { ApiClientError } from '../../lib/api/client'
import type { PromptRun } from '../../types/runs'
import { useAuth } from '../auth/auth-context'

const demoMode = import.meta.env.MODE === 'test' && import.meta.env.VITE_USE_MOCK_RUNS !== 'false'

export function PlaygroundPage() {
  const { user } = useAuth()
  const [params] = useSearchParams()
  const [versionId, setVersionId] = useState(params.get('version') ?? Object.values(versionStore).flat()[0]?.id ?? '')
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [scenario, setScenario] = useState<'normal' | 'failed' | 'blocked'>('normal')
  const [run, setRun] = useState<PromptRun | null>(null)
  const [error, setError] = useState('')
  const [executionError, setExecutionError] = useState<'blocked' | 'failed' | null>(null)
  const [pending, setPending] = useState(false)
  const selected = useMemo(() => Object.values(versionStore).flat().find((version) => version.id === versionId), [versionId])

  async function execute() {
    if (!selected) return setError('Select a prompt version.')
    const missing = selected.variables.find((variable) => variable.required && !inputs[variable.name]?.trim())
    if (missing) return setError(`${missing.name} is required.`)
    setPending(true); setError(''); setRun(null); setExecutionError(null)
    try { setRun(await runService.create({ version_id: selected.id, variables: inputs }, scenario, user?.id)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'The run could not be completed. Try again.'); setExecutionError(cause instanceof ApiClientError && cause.code === 'budget_exceeded' ? 'blocked' : 'failed') }
    finally { setPending(false) }
  }

  return <><PageHeader title="Playground" description="Test a prompt version with variables before deploying." />
    <div className="playground">
      <section className="panel"><div className="panel-head"><div><h2>Prompt configuration</h2><p>Select an immutable version to run.</p></div>{demoMode && <Status>Demo provider</Status>}</div>
        <label className="field"><span>Prompt version</span><select value={versionId} onChange={(event) => { setVersionId(event.target.value); setInputs({}); setRun(null); setError('') }}>
          {Object.values(versionStore).flat().map((version) => <option key={version.id} value={version.id}>{promptStore.find((prompt) => prompt.id === version.prompt_id)?.key ?? version.prompt_id} · v{version.version_number}</option>)}
        </select></label>
        {selected?.variables.map((variable) => <label className="field" key={variable.name}><span>{variable.name}{variable.required ? ' *' : ' (optional)'}</span><textarea value={inputs[variable.name] ?? ''} onChange={(event) => setInputs({ ...inputs, [variable.name]: event.target.value })} placeholder={variable.description || variable.default_value || `Enter ${variable.name}`} /></label>)}
        {demoMode && <label className="field"><span>Test scenario</span><select aria-label="Test scenario" value={scenario} onChange={(event) => setScenario(event.target.value as typeof scenario)}><option value="normal">Successful run</option><option value="failed">Provider failure</option><option value="blocked">Budget limit</option></select></label>}
        {error && !executionError && <p className="form-error" role="alert">{error}</p>}
        <Button onClick={execute} disabled={pending || !selected}>{pending ? 'Running…' : 'Run prompt'}</Button>
      </section>
      <section className="panel output" aria-live="polite"><div className="panel-head"><div><h2>Output</h2><p>{run ? `Run ${run.id}` : 'Your response will appear here.'}</p></div>{run && <Status tone={run.status === 'completed' ? 'success' : 'warning'}>{run.status}</Status>}</div>
        {run?.status === 'completed' ? <><div className="output-copy">{run.output}</div><div className="metrics"><Stat label="PROMPT TOKENS" value={String(run.prompt_tokens ?? 0)} note="" /><Stat label="COMPLETION TOKENS" value={String(run.completion_tokens ?? 0)} note="" /><Stat label="LATENCY" value={`${((run.latency_ms ?? 0) / 1000).toFixed(2)}s`} note="" /></div><Link className="run-detail-link" to={`/runs/${run.id}`}>View run details →</Link></> : run ? <div className="run-outcome"><h3>{run.status === 'blocked' ? 'Budget limit reached' : 'Run failed'}</h3><p>{run.error_message}</p><Link to={`/runs/${run.id}`}>View run details →</Link></div> : executionError ? <div className="run-outcome" role="alert"><h3>{executionError === 'blocked' ? 'Budget limit reached' : 'Run failed'}</h3><p>{error}</p></div> : <div className="empty-output">Run a prompt to see the response and execution metrics.</div>}
      </section>
    </div></>
}
