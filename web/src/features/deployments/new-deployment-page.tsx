import { useEffect, useRef, useState, useSyncExternalStore, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { PageHeader } from '../../components/layout/page-header'
import { Button } from '../../components/ui/prototype'
import { useAuth } from '../auth/auth-context'
import { evaluationApi, defaults, type Improvement, type Setup, type TestCase } from '../evaluations/evaluation-api'
import { promptStore, versionStore, workspaceService, workspaceStore } from '../projects/workspace-data'
import type { DeploymentEnvironment } from '../../types/deployments'
import { deploymentService } from './deployment-service'
import { deploymentsApi } from './api'
import { releaseValidationApi, type ReleaseValidation } from './release-validation-api'
import { ReleaseValidationPanel } from './release-validation-panel'

const backendEnvironment = (value: DeploymentEnvironment) => value === 'production' ? 'prod' : value === 'development' ? 'dev' : 'staging'
const blankCase = (): TestCase => ({ name: 'Typical request', variables: {}, reference: '' })

export function NewDeploymentPage() {
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot)
  const { user } = useAuth()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [versionId, setVersionId] = useState(params.get('version') ?? Object.values(versionStore).flat()[0]?.id ?? '')
  const initialEnvironment = params.get('environment')
  const [environment, setEnvironment] = useState<DeploymentEnvironment>(initialEnvironment === 'production' || initialEnvironment === 'development' ? initialEnvironment : 'staging')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const busy = useRef(false)
  const [report, setReport] = useState<ReleaseValidation | null>(null)
  const [draft, setDraft] = useState<Improvement | null>(null)
  const [saved, setSaved] = useState<{ promptId: string; configuration: Setup | null } | null>(null)
  const [useSaved, setUseSaved] = useState(true)
  const [goal, setGoal] = useState('Answer the request accurately, clearly, and follow the prompt instructions.')
  const [cases, setCases] = useState<TestCase[]>([blankCase()])
  const [maxWords, setMaxWords] = useState('')
  const [validJson, setValidJson] = useState(false)
  const [requiredFields, setRequiredFields] = useState('')
  const [weights, setWeights] = useState(defaults)
  const hydratedReport = useRef<string | null>(null)
  const candidate = Object.values(versionStore).flat().find((version) => version.id === versionId)
  const reportId = params.get('validation')
  const existingDeployment = params.get('deployment')
  const suiteReady = saved?.promptId === candidate?.prompt_id
  const savedSuite = suiteReady ? saved?.configuration : null
  const currentReport = report?.version_id === versionId && report.environment === backendEnvironment(environment) ? report : null
  const running = currentReport?.status === 'queued' || currentReport?.status === 'running'

  useEffect(() => {
    if (!candidate) return
    const controller = new AbortController()
    evaluationApi.setup(candidate.prompt_id, controller.signal).then(({ configuration }) => {
      if (!controller.signal.aborted) setSaved({ promptId: candidate.prompt_id, configuration })
    }).catch((cause) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Could not load saved tests.') })
    return () => controller.abort()
  }, [candidate])
  useEffect(() => {
    if (!reportId) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    async function poll() {
      try {
        const next = await releaseValidationApi.get(reportId!, controller.signal)
        if (controller.signal.aborted) return
        setReport(next)
        if (hydratedReport.current !== next.id && next.configuration) {
          hydratedReport.current = next.id
          setUseSaved(false)
          setGoal(next.configuration.goal)
          setCases(next.configuration.cases)
          setMaxWords(next.configuration.requirements.max_words?.toString() ?? '')
          setValidJson(next.configuration.requirements.valid_json)
          setRequiredFields(next.configuration.requirements.required_fields.join(', '))
          setWeights(next.configuration.weights)
        }
        if (next.status === 'queued' || next.status === 'running') timer = setTimeout(poll, 1500)
      } catch (cause) { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Could not load validation.') }
    }
    void poll()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [reportId])

  function clearReport() {
    setReport(null); setDraft(null); setError('')
    setParams((current) => { const next = new URLSearchParams(current); next.delete('validation'); return next }, { replace: true })
  }
  async function validate(event?: FormEvent) {
    event?.preventDefault()
    if (!candidate || busy.current) return
    busy.current = true; setPending(true); setError(''); setDraft(null)
    try {
      const result = await releaseValidationApi.start({ id: crypto.randomUUID(), version_id: versionId, environment: backendEnvironment(environment),
        ...(useSaved && savedSuite ? {} : { suite: { goal, cases: cases.map((testCase) => ({ ...testCase, variables: Object.fromEntries(candidate.variables.map(({ name }) => [name, testCase.variables[name] ?? ''])) })), weights, requirements: { max_words: maxWords ? Number(maxWords) : null, valid_json: validJson, required_fields: validJson ? requiredFields.split(',').map((field) => field.trim()).filter(Boolean) : [] } } }) })
      setReport(result)
      setParams((current) => { const next = new URLSearchParams(current); next.set('version', versionId); next.set('environment', environment); next.set('validation', result.id); return next }, { replace: true })
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not validate release.') }
    finally { busy.current = false; setPending(false) }
  }
  async function deploy() {
    if (!currentReport || currentReport.status !== 'passed' || busy.current) return
    busy.current = true; setPending(true); setError('')
    try {
      if (existingDeployment) {
        await deploymentsApi.revalidate(existingDeployment, currentReport.id)
        navigate(`/deployments/${existingDeployment}`)
      } else {
        const item = await deploymentService.create({ version_id: versionId, environment, note, validation_id: currentReport.id }, user)
        navigate(`/deployments/${item.id}`)
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not request deployment.')
      try { setReport(await releaseValidationApi.get(currentReport.id)) } catch { /* Keep the original action error visible. */ }
    } finally { busy.current = false; setPending(false) }
  }
  async function suggestFix() {
    if (!currentReport || busy.current) return
    busy.current = true; setPending(true); setError('')
    try { setDraft(await releaseValidationApi.fix(currentReport.id)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not suggest a fix.') }
    finally { busy.current = false; setPending(false) }
  }
  async function saveFix() {
    if (!candidate || !draft || busy.current) return
    busy.current = true; setPending(true); setError('')
    try {
      const next = await workspaceService.createVersion(candidate.prompt_id, { parent_version_id: candidate.id, template: draft.template, model_config: candidate.model_config, commit_message: 'Address release validation failures' })
      setVersionId(next.id); clearReport()
      // A fix changes the immutable candidate, so it gets a new report and request.
      setParams((current) => { const query = new URLSearchParams(current); query.delete('deployment'); query.delete('validation'); query.set('version', next.id); return query }, { replace: true })
      const configuration = currentReport?.configuration
      if (configuration) {
        const checked = await releaseValidationApi.start({ id: crypto.randomUUID(), version_id: next.id, environment: backendEnvironment(environment), suite: { goal: configuration.goal, cases: configuration.cases, weights: configuration.weights, requirements: configuration.requirements } })
        setReport(checked)
        setParams((current) => { const query = new URLSearchParams(current); query.delete('deployment'); query.set('version', next.id); query.set('environment', environment); query.set('validation', checked.id); return query }, { replace: true })
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save the fix.') }
    finally { busy.current = false; setPending(false) }
  }
  function updateCase(index: number, patch: Partial<TestCase>) {
    clearReport(); setCases((current) => current.map((testCase, i) => i === index ? { ...testCase, ...patch } : testCase))
  }
  return <><PageHeader title={existingDeployment ? 'Revalidate deployment' : 'Create deployment'} eyebrow="DEPLOYMENTS" description="Validate the candidate, review the evidence, then request deployment." />
    {error && <p className="form-error" role="alert">{error}</p>}
    <form className="form-panel release-request-form" onSubmit={validate}>
      <label className="field"><span>Prompt version</span><select disabled={pending || running || !!existingDeployment} value={versionId} onChange={(event) => { setVersionId(event.target.value); clearReport() }}><option value="" disabled>Select a version</option>{Object.values(versionStore).flat().map((version) => <option value={version.id} key={version.id}>{promptStore.find((prompt) => prompt.id === version.prompt_id)?.key ?? version.prompt_id} · v{version.version_number}</option>)}</select></label>
      <label className="field"><span>Environment</span><select disabled={pending || running || !!existingDeployment} value={environment} onChange={(event) => { setEnvironment(event.target.value as DeploymentEnvironment); clearReport() }}><option value="development">Development</option><option value="staging">Staging</option><option value="production">Production (requires approval)</option></select></label>
      <p className="deployment-hint">Target model: {candidate?.model_config.model ?? 'Select a version'}. Uses this immutable version’s Gemini configuration. Production needs Admin approval after validation.</p>
      <fieldset className="release-tests" disabled={pending || running}><legend>Release tests</legend>
        {!suiteReady ? <p role="status">Loading saved test suite…</p> : savedSuite && <><label className="check"><input type="checkbox" checked={useSaved} onChange={(event) => { setUseSaved(event.target.checked); clearReport() }} />Use saved evaluation tests ({savedSuite.cases.length} cases)</label>{useSaved && <p>{savedSuite.goal}</p>}</>}
        {(!savedSuite || !useSaved) && <>
          <label className="field"><span>What should a successful answer do?</span><textarea required minLength={10} maxLength={2000} value={goal} onChange={(event) => { setGoal(event.target.value); clearReport() }} /></label>
          {cases.map((testCase, index) => <div className="release-case" key={index}>
            <label className="field"><span>Test {index + 1} name</span><input required maxLength={100} value={testCase.name} onChange={(event) => updateCase(index, { name: event.target.value })} /></label>
            {candidate?.variables.map(({ name: variable }) => <label className="field" key={variable}><span>Test {index + 1}: {variable}</span><textarea required maxLength={2000} value={testCase.variables[variable] ?? ''} onChange={(event) => updateCase(index, { variables: { ...testCase.variables, [variable]: event.target.value } })} /></label>)}
            <label className="field"><span>Test {index + 1} expected answer (optional)</span><textarea maxLength={3000} value={testCase.reference} onChange={(event) => updateCase(index, { reference: event.target.value })} /></label>
            {cases.length > 1 && <Button secondary type="button" onClick={() => { setCases((current) => current.filter((_, i) => i !== index)); clearReport() }}>Remove test {index + 1}</Button>}
          </div>)}
          {cases.length < 5 && <Button secondary type="button" onClick={() => { setCases((current) => [...current, { ...blankCase(), name: `Test ${current.length + 1}` }]); clearReport() }}>Add test case</Button>}
          <label className="field"><span>Maximum words (optional)</span><input type="number" min={1} max={10000} value={maxWords} onChange={(event) => { setMaxWords(event.target.value); clearReport() }} /></label>
          <label className="check"><input type="checkbox" checked={validJson} onChange={(event) => { setValidJson(event.target.checked); clearReport() }} />Require valid JSON</label>
          {validJson && <label className="field"><span>Required JSON fields (comma separated, optional)</span><input value={requiredFields} onChange={(event) => { setRequiredFields(event.target.value); clearReport() }} /></label>}
        </>}
        <p className="deployment-hint">Up to five cases. Each case uses one generation and one Gemini assessment. All required checks and a score of at least 70/100 must pass. Without an expected answer, factual correctness is not scored.</p>
      </fieldset>
      <label className="field"><span>Deployment note</span><textarea disabled={pending} value={note} maxLength={2000} onChange={(event) => setNote(event.target.value)} placeholder="What changed in this deployment?" /></label>
      <div className="form-actions"><Button secondary type="button" onClick={() => navigate('/deployments')}>Cancel</Button><Button type="submit" disabled={pending || running || !candidate || !suiteReady}>{pending ? 'Working…' : running ? 'Validating…' : currentReport ? 'Validate again' : 'Validate release'}</Button></div>
    </form>
    {currentReport && <><ReleaseValidationPanel report={currentReport} />
      {currentReport.status === 'blocked' && <div className="release-actions">{currentReport.evaluation?.results.some((result) => result.weighted_score !== null) && <Button secondary disabled={pending || !!draft} onClick={suggestFix}>Suggest a fix</Button>}<p>Correct failed settings or test inputs above, or <Link to={`/versions/${versionId}`}>open the version</Link> to review its input contract. Provider failures can be retried with Validate again.</p></div>}
      {draft && <section className="panel release-validation"><h2>Suggested fix</h2><p>{draft.explanation}</p><p>This draft has not been tested. Review the changes before saving.</p><div className="release-diff"><label className="field"><span>Current prompt</span><textarea readOnly value={candidate?.template ?? ''} /></label><label className="field"><span>Proposed prompt</span><textarea value={draft.template} onChange={(event) => setDraft({ ...draft, template: event.target.value })} /></label></div><Button disabled={pending || !draft.template.trim()} onClick={saveFix}>Save fix and validate</Button><p>Saves a new version and runs these tests again before deployment.</p></section>}
      {currentReport.status === 'passed' && <div className="form-actions"><Button disabled={pending} onClick={deploy}>{pending ? 'Submitting…' : existingDeployment ? 'Attach updated validation' : environment === 'production' ? 'Request approval' : 'Create deployment'}</Button></div>}
    </>}
  </>
}
