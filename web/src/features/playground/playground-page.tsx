import { LLM_PROVIDERS } from '../../lib/providers'
import { useProviderModels } from './provider-models'
import { workspaceService } from '../projects/workspace-data'
import type { ModelConfig } from '../../types/prompts'
import { useState, useSyncExternalStore } from 'react'
import { useSearchParams } from 'react-router-dom'
import { PageHeader } from '../../components/layout/page-header'
import { Button, Stat, Status } from '../../components/ui/prototype'
import { promptStore, versionStore, workspaceStore } from '../projects/workspace-data'
import { runService } from '../runs/run-service'
import { ApiClientError } from '../../lib/api/client'
import type { PromptRun } from '../../types/runs'
import { useAuth } from '../auth/auth-context'

const demoMode = import.meta.env.MODE === 'test' && import.meta.env.VITE_USE_MOCK_RUNS !== 'false'

const DEMO_INPUTS: Record<string, string> = {
  customer_name: 'Priya Sharma',
  order_number: 'PV-2026-1042',
  order_status: 'In transit — delayed at the regional sorting center',
  estimated_delivery: 'October 17, 2026',
  additional_context: 'Carrier tracking has not updated for 24 hours after the package reached the Bengaluru regional sorting center. No delivery attempt has been recorded.',
  support_channel: 'email',
  escalation_required: 'yes',
  customer_message: 'My order is delayed and tracking has not changed since yesterday. Can you tell me what happens next?',
  order_context: 'Order PV-2026-1042 is in transit at the Bengaluru regional sorting center. Estimated delivery is October 17, 2026.',
}

export function PlaygroundPage() {
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot)
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const [versionId, setVersionId] = useState(params.get('version') ?? Object.values(versionStore).flat()[0]?.id ?? '')
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [scenario, setScenario] = useState<'normal' | 'failed' | 'blocked'>('normal')
  const [run, setRun] = useState<PromptRun | null>(null)
  const [error, setError] = useState('')
  const [executionError, setExecutionError] = useState<'blocked' | 'failed' | null>(null)
  const [pending, setPending] = useState(false)
  const selected = Object.values(versionStore).flat().find((version) => version.id === versionId)
  const discovery = useProviderModels()
  const [draft, setDraft] = useState<{ versionId: string; config: ModelConfig } | null>(null)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  const config = draft?.versionId === selected?.id ? draft?.config : selected?.model_config
  const providerInfo = discovery.data?.items.find((item) => item.provider === config?.provider)
  const modelInfo = providerInfo?.models.find((item) => item.id === config?.model)
  const canLoadDemoInputs = Boolean(selected?.variables.length && selected.variables.every((variable) => !variable.required || DEMO_INPUTS[variable.name]))
  const changed = Boolean(selected && config && JSON.stringify(config) !== JSON.stringify(selected.model_config))
  const internalMock = config?.provider === 'mock' && (import.meta.env.DEV || import.meta.env.MODE === 'test')
  const unavailable = internalMock ? '' : discovery.error || (!discovery.data ? 'Loading provider models…' :
    !modelInfo ? 'Select a supported free-access model.' : modelInfo.unavailable_reason ?? '')

  function changeConfig(patch: Partial<ModelConfig>) {
    if (!selected || !config) return
    setDraft({ versionId: selected.id, config: { ...config, ...patch } })
    setRun(null); setError(''); setNotice('')
  }

  async function saveConfiguration() {
    if (!selected || !config || !changed || saving) return
    setSaving(true); setError(''); setNotice('')
    try {
      const version = await workspaceService.createVersion(selected.prompt_id, {
        parent_version_id: selected.id, template: selected.template, model_config: config,
        commit_message: `Configure ${config.provider} / ${config.model} in Playground`,
      })
      setVersionId(version.id); setParams({ version: version.id }); setDraft(null); setRun(null)
      setNotice(`Configuration saved as version ${version.version_number}.`)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save configuration.') }
    finally { setSaving(false) }
  }


  async function execute() {
    if (!selected) return setError('Select a prompt version.')
    if (changed) return setError('Save the configuration as a new version before running.')
    if (unavailable) return setError(unavailable)
    const missing = selected.variables.find((variable) => variable.required && !inputs[variable.name]?.trim())
    if (missing) return setError(`${missing.name} is required.`)
    setPending(true); setError(''); setRun(null); setExecutionError(null)
    try { setRun(await runService.create({ version_id: selected.id, variables: inputs }, scenario, user?.id)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'The run could not be completed. Try again.'); setExecutionError(cause instanceof ApiClientError && cause.code === 'budget_exceeded' ? 'blocked' : 'failed') }
    finally { setPending(false) }
  }

  return <><PageHeader title="Playground" description="Test immutable prompt versions with free-access models." />
    <div className="playground">
      <section className="panel"><div className="panel-head"><div><h2>Prompt configuration</h2><p>Select an immutable version to run.</p></div>{demoMode && <Status>Demo provider</Status>}</div>
        <label className="field"><span>Prompt version</span><select disabled={pending || saving} value={versionId} onChange={(event) => { setVersionId(event.target.value); setParams({ version: event.target.value }); setInputs({}); setRun(null); setError('') }}>
          {Object.values(versionStore).flat().map((version) => <option key={version.id} value={version.id}>{promptStore.find((prompt) => prompt.id === version.prompt_id)?.key ?? version.prompt_id} · v{version.version_number}</option>)}
        </select></label>
        {config && <>
          <label className="field"><span>LLM provider</span><select value={config.provider} disabled={pending || saving || (!discovery.data && !demoMode)} onChange={(event) => {
            const provider = event.target.value
            const first = discovery.data?.items.find((item) => item.provider === provider)?.models[0]
            changeConfig({ provider, model: first?.id ?? '', max_output_tokens: Math.min(config.max_output_tokens ?? 500, first?.max_output_tokens ?? 4096) })
          }}>
            {LLM_PROVIDERS.map((provider) => <option key={provider} value={provider}>{provider}</option>)}
            {internalMock && <option value="mock">Mock (local testing)</option>}
          </select></label>
          <label className="field"><span>Model</span><select value={modelInfo ? config.model : ''} disabled={pending || saving || internalMock} onChange={(event) => changeConfig({ model: event.target.value })}>
            {!modelInfo && <option value="" disabled>Select a supported model</option>}
            {providerInfo?.models.map((model) => <option key={model.id} value={model.id}>{model.label}</option>)}
          </select></label>
          <label className="field"><span>Maximum output tokens</span><input type="number" min={1} max={modelInfo?.max_output_tokens ?? 4096} value={config.max_output_tokens ?? 500} disabled={pending || saving} onChange={(event) => changeConfig({ max_output_tokens: Number(event.target.value) })} /></label>
          <label className="field"><span>Temperature</span><input type="number" min={0} max={2} step={0.1} value={config.temperature ?? 0} disabled={pending || saving} onChange={(event) => changeConfig({ temperature: Number(event.target.value) })} /></label>
          {providerInfo && <p className="provider-note">{providerInfo.quota_note}</p>}
          {modelInfo && <p className="provider-note">Up to {modelInfo.max_input_characters.toLocaleString()} prompt characters · {discovery.data?.timeout_seconds}s timeout</p>}
          {unavailable && <p className="provider-note" role="status">{unavailable}</p>}
          {internalMock && discovery.error && <p className="provider-note" role="status">{discovery.error}</p>}
          {changed && <Button onClick={saveConfiguration} disabled={saving || pending || Boolean(unavailable) || !config.model || !Number.isInteger(config.max_output_tokens) || (config.max_output_tokens ?? 0) < 1 || (config.max_output_tokens ?? 0) > (modelInfo?.max_output_tokens ?? 4096)}>{saving ? 'Saving…' : 'Save configuration'}</Button>}
          {notice && <p className="provider-note" role="status">{notice}</p>}
        </>}
        {canLoadDemoInputs && <div className="demo-inputs"><div><b>Demo scenario</b><p>Delayed order at a regional sorting center, with an email response and support escalation.</p></div><Button secondary disabled={pending || saving} onClick={() => setInputs(Object.fromEntries(selected!.variables.map((variable) => [variable.name, DEMO_INPUTS[variable.name] ?? variable.default_value ?? ''])))}>Load demo inputs</Button></div>}
        {selected?.variables.map((variable) => <label className="field" key={variable.name}><span>{variable.name}{variable.required ? ' *' : ' (optional)'}</span><textarea disabled={pending || saving} value={inputs[variable.name] ?? ''} onChange={(event) => setInputs({ ...inputs, [variable.name]: event.target.value })} placeholder={variable.description || variable.default_value || `Enter ${variable.name}`} /></label>)}
        {demoMode && <label className="field"><span>Test scenario</span><select aria-label="Test scenario" value={scenario} onChange={(event) => setScenario(event.target.value as typeof scenario)}><option value="normal">Successful run</option><option value="failed">Provider failure</option><option value="blocked">Budget limit</option></select></label>}
        {error && !executionError && <p className="form-error" role="alert">{error}</p>}
        <div className="playground-actions">
          {!demoMode && <button className="text-button" type="button" onClick={discovery.refresh}>Refresh providers</button>}
          <Button onClick={execute} disabled={pending || saving || !selected || changed || Boolean(unavailable)}>{pending ? 'Running…' : 'Run prompt'}</Button>
        </div>
      </section>
      <section className="panel output" aria-live="polite"><div className="panel-head"><div><h2>Output</h2><p>{run ? `Run ${run.id}` : 'Your response will appear here.'}</p></div>{run && <Status tone={run.status === 'completed' ? 'success' : 'warning'}>{run.status}</Status>}</div>
        {run?.status === 'completed' ? <><div className="output-copy">{run.output}</div><div className="metrics"><Stat label="PROMPT TOKENS" value={String(run.prompt_tokens ?? 0)} note="" /><Stat label="COMPLETION TOKENS" value={String(run.completion_tokens ?? 0)} note="" /><Stat label="LATENCY" value={`${((run.latency_ms ?? 0) / 1000).toFixed(2)}s`} note="" /></div></> : run ? <div className="run-outcome"><h3>{run.status === 'blocked' ? 'Budget limit reached' : 'Run failed'}</h3><p>{run.error_message}</p></div> : executionError ? <div className="run-outcome" role="alert"><h3>{executionError === 'blocked' ? 'Budget limit reached' : 'Run failed'}</h3><p>{error}</p></div> : <div className="empty-output">Run a prompt to see the response and execution metrics.</div>}
      </section>
    </div></>
}
