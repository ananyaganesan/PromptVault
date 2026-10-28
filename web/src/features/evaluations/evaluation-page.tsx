import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { PageHeader } from '../../components/layout/page-header'
import { EmptyState } from '../../components/ui/empty-state'
import { Button, Status } from '../../components/ui/prototype'
import { apiClient } from '../../lib/api/client'
import { refreshLiveData } from '../../lib/live-refresh'
import { promptFor, versionsFor, workspaceService, workspaceStore } from '../projects/workspace-data'
import type { Page } from '../../types/api'
import {
  evaluationApi, metricLabel, metricNames, metricDefinitions, presets, defaults,
  type Evaluation, type HistoryItem, type Improvement, type Preset, type Requirements, type Setup, type SuggestedSetup, type TestCase,
} from './evaluation-api'
import './evaluations.css'

const running = (evaluation: Evaluation | null) => evaluation?.status === 'queued' || evaluation?.status === 'running'
const message = (cause: unknown) => cause instanceof Error ? cause.message : 'The request could not be completed.'
function newCase(names: string[], index: number): TestCase {
  return { name: `Scenario ${index}`, variables: Object.fromEntries(names.map((name) => [name, ''])), reference: '' }
}

function ExampleInputs({ values }: { values: Record<string, string> }) {
  return <dl className="eval-example-inputs">{Object.entries(values).map(([name, value]) => <div key={name}><dt>{name.replace(/_/g, ' ')}</dt><dd>{value || 'No input added yet.'}</dd></div>)}</dl>
}

function AnswerRules({ requirements }: { requirements: Requirements }) {
  return <div className="eval-muted">
    {requirements.max_words && <p>Keep each answer within {requirements.max_words} words.</p>}
    {requirements.valid_json && <p>Answers must use a consistent, organized format{requirements.required_fields.length ? ` and include: ${requirements.required_fields.join(', ')}` : ''}.</p>}
  </div>
}

function checkDescription(check: { name: string; passed: boolean; detail: string }) {
  if (check.name === 'Valid JSON') return check.passed ? 'Answer follows the expected format.' : 'Answer does not follow the expected format.'
  if (check.name.startsWith('Field: ')) return `${check.passed ? 'Includes' : 'Missing'}: ${check.name.slice('Field: '.length)}`
  return check.detail
}

export function EvaluationPage() {
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot)
  const { promptId } = useParams()
  const prompt = promptFor(promptId)
  if (!prompt) return <EmptyState title="Prompt not found" description="Open a prompt from your project to evaluate its versions." action={<Link to="/prompts">Back to prompts</Link>} />
  return <EvaluationContent key={prompt.id} promptId={prompt.id} name={prompt.name} />
}

function EvaluationContent({ promptId, name }: { promptId: string; name: string }) {
  const versions = versionsFor(promptId)
  const [query, setQuery] = useSearchParams()
  const evaluationId = query.get('evaluation')
  const initialIds = versions.slice(0, 2).map((v) => v.id)
  const initialVariables = [...new Set(versions.filter((v) => initialIds.includes(v.id)).flatMap((v) => v.variables.map((variable) => variable.name)))]
  const [setup, setSetup] = useState<Setup>({ use_embeddings: true, version_ids: initialIds, goal: presets.accurate_answers.goal, preset: 'accurate_answers', cases: [newCase(initialVariables, 1)], weights: { ...defaults }, requirements: { valid_json: false, required_fields: [], max_words: null } })
  const [ready, setReady] = useState(false)
  const [expandedCases, setExpandedCases] = useState<number[]>([0])
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [evaluationSnapshot, setEvaluation] = useState<Evaluation | null>(null)
  const evaluation = evaluationSnapshot?.id === evaluationId ? evaluationSnapshot : null
  const [suggestion, setSuggestion] = useState<SuggestedSetup | null>(null)
  const [draftSnapshot, setDraft] = useState<(Improvement & { versionId: string; evaluationId: string }) | null>(null)
  const draft = draftSnapshot?.evaluationId === evaluationId ? draftSnapshot : null
  const [improveId, setImproveId] = useState('')
  const [commit, setCommit] = useState('Improve prompt from evaluation findings')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [retry, setRetry] = useState(0)
  const request = useRef<{ id: string; fingerprint: string } | null>(null)
  const pending = useRef(false)
  const reportRef = useRef<HTMLElement>(null)
  const scrolledReport = useRef<string | null>(null)
  useEffect(() => {
    if (evaluation && scrolledReport.current !== evaluation.id) {
      reportRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
      reportRef.current?.focus({ preventScroll: true })
      scrolledReport.current = evaluation.id
    }
  }, [evaluation])
  const active = Boolean(busy) || running(evaluation)
  const names = [...new Set(versions.filter((v) => setup.version_ids.includes(v.id)).flatMap((v) => v.variables.map((variable) => variable.name)))]

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([evaluationApi.setup(promptId, controller.signal), evaluationApi.history(promptId, controller.signal)])
      .then(([saved, items]) => {
        if (controller.signal.aborted) return
        if (saved.configuration) {
          setSetup({ ...saved.configuration, use_embeddings: true })
          setExpandedCases(saved.configuration.cases.some((test) => Object.values(test.variables).some(Boolean) || test.reference) ? [] : [0])
        }
        setHistory(items); setReady(true); setError('')
      }).catch((cause) => { if (!controller.signal.aborted) { setError(message(cause)); setReady(false) } })
    return () => controller.abort()
  }, [promptId, retry])

  useEffect(() => {
    if (!evaluationId) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      try {
        const item = await evaluationApi.get(promptId, evaluationId, controller.signal)
        if (controller.signal.aborted) return
        setEvaluation(item)
        setImproveId((current) => item.configuration.version_ids.includes(current) ? current : item.winner_version_id ?? item.configuration.version_ids[0])
        if (running(item)) timer = setTimeout(() => { void poll() }, 1500)
        else setHistory(await evaluationApi.history(promptId, controller.signal))
      } catch (cause) { if (!controller.signal.aborted) setError(message(cause)) }
    }
    void poll()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [promptId, evaluationId, retry])

  function changeVersions(id: string) {
    const ids = setup.version_ids.includes(id) ? setup.version_ids.filter((item) => item !== id) : [...setup.version_ids, id]
    const variables = [...new Set(versions.filter((v) => ids.includes(v.id)).flatMap((v) => v.variables.map((variable) => variable.name)))]
    setSetup({ ...setup, version_ids: ids, cases: setup.cases.map((test) => ({ ...test, variables: Object.fromEntries(variables.map((key) => [key, test.variables[key] ?? ''])) })) })
    setSuggestion(null)
  }
  function updateCase(index: number, update: Partial<TestCase>) {
    setSetup({ ...setup, cases: setup.cases.map((item, i) => i === index ? { ...item, ...update } : item) })
  }
  function validate() {
    if (setup.version_ids.length < 2 || setup.version_ids.length > 5) throw new Error('Choose two to five versions.')
    if (setup.version_ids.some((id) => !versions.some((v) => v.id === id))) throw new Error('Choose available versions before evaluating.')
    if (setup.goal.trim().length < 10) throw new Error('Describe the desired output in at least 10 characters.')
    if (setup.cases.length * setup.version_ids.length > 15) throw new Error('Compare at most 15 answers at a time. Choose fewer versions or scenarios.')
    if (Object.values(setup.weights).some((value) => !Number.isInteger(value) || value < 0 || value > 100) || Object.values(setup.weights).reduce((a, b) => a + b, 0) !== 100) throw new Error('Choose whole-number priorities totaling 100%.')
    if (setup.cases.some((test) => !test.name.trim())) throw new Error('Give every scenario a name.')
    if (new Set(setup.cases.map((test) => test.name.trim().toLowerCase())).size !== setup.cases.length) throw new Error('Give each scenario a different name.')
  }
  async function action(label: string, operation: () => Promise<void>) {
    if (pending.current) return
    pending.current = true; setBusy(label); setError(''); setNotice('')
    try { await operation() } catch (cause) { setError(message(cause)) }
    finally { pending.current = false; setBusy('') }
  }
  async function start() {
    await action('Starting evaluation', async () => {
      validate()
      const configuration = normalizedSetup(setup)
      const fingerprint = JSON.stringify(configuration)
      if (request.current?.fingerprint !== fingerprint) request.current = { id: crypto.randomUUID(), fingerprint }
      const item = await evaluationApi.start(promptId, request.current!.id, configuration)
      setEvaluation(item); setQuery({ evaluation: item.id }); request.current = null
    })
  }
  async function reuseRuns() {
    await action('Loading previous inputs', async () => {
      const page = await apiClient.request<Page<{ id: string; input_variables: Record<string, string> }>>('/runs', { query: { prompt_id: promptId, status: 'completed', page_size: 5 } })
      if (!page.items.length) { setNotice('No previous runs are available yet. Add a scenario below or ask Gemini to suggest some.'); return }
      const cases = page.items.slice(0, Math.min(5, Math.floor(15 / Math.max(2, setup.version_ids.length)))).map((run, i) => ({ name: `Previous run ${i + 1} (${run.id.slice(-6)})`, variables: Object.fromEntries(names.map((key) => [key, run.input_variables[key] ?? ''])), reference: '' }))
      setSetup({ ...setup, cases }); setExpandedCases([0]); setNotice('Inputs from past runs loaded. Review each scenario and add an expected answer only if you know it is correct.')
    })
  }
  const label = (id: string) => `v${evaluation?.version_snapshots.find((v) => v.id === id)?.version_number ?? versions.find((v) => v.id === id)?.version_number ?? '?'}`
  const total = setup.version_ids.length * setup.cases.length
  return <div className="evaluation-page">
    <PageHeader title="Prompt evaluation" eyebrow="PROMPT EVALUATION" description={`${name} · Compare saved versions using situations your prompt needs to handle.`} />
    {error && <div className="eval-notice error" role="alert"><p>{error}</p><Button secondary onClick={() => setRetry((value) => value + 1)}>Reload evaluation data</Button></div>}
    {notice && <p className="eval-notice" role="status">{notice}</p>}
    {!ready ? <p role="status">{error ? 'Evaluation setup could not be loaded.' : 'Loading evaluation setup…'}</p> : <section className="eval-setup" aria-label="Evaluation setup">
      <fieldset id="eval-step-versions" className="eval-step eval-goal-step" disabled={active}>
        <legend>1. Choose versions and your goal</legend>
        <p className="eval-muted">Select two to five versions. Describe the outcome you want from a good answer.</p><div className="eval-version-options">{versions.map((version) => <label key={version.id} className="eval-version-option"><input type="checkbox" checked={setup.version_ids.includes(version.id)} onChange={() => changeVersions(version.id)} /><span><b>v{version.version_number}</b><small>{version.commit_message}</small></span></label>)}</div>
        {versions.length < 2 && <p>Create at least two versions before comparing.</p>}
        <div className="eval-goal-fields"><label className="field"><span>What are you using this prompt for?</span><select value={setup.preset} onChange={(event) => {
          const preset = event.target.value as Preset
          setSetup({ ...setup, preset, goal: presets[preset].goal, weights: { ...presets[preset].weights }, requirements: { ...setup.requirements, valid_json: preset === 'structured_json', required_fields: [] } }); setSuggestion(null)
        }}>{Object.entries(presets).map(([key, item]) => <option value={key} key={key}>{item.label}</option>)}</select></label>
        <label className="field"><span>What should a good answer achieve?</span><textarea maxLength={2000} value={setup.goal} onChange={(event) => { setSetup({ ...setup, goal: event.target.value }); setSuggestion(null) }} /></label></div>

      </fieldset>
      <fieldset id="eval-step-examples" className="eval-step eval-examples-step" disabled={active}><legend>2. Add your test scenarios</legend>
        <Button secondary className="button secondary eval-add-case" disabled={setup.cases.length >= 5} onClick={() => { setExpandedCases([...expandedCases, setup.cases.length]); setSetup({ ...setup, cases: [...setup.cases, newCase(names, setup.cases.length + 1)] }) }}>Add another scenario</Button>
        <p className="eval-muted">Choose situations from your own work: a common request, an edge case, or a difficult question. Enter the information your prompt would receive. Every version gets the same inputs. Add an expected answer only when you can verify it; otherwise we can assess usefulness but cannot verify the facts.</p>
        {setup.cases.map((test, index) => <details className="eval-case" key={index} open={expandedCases.includes(index)}>
          <summary onClick={(event) => { event.preventDefault(); setExpandedCases((current) => current.includes(index) ? current.filter((i) => i !== index) : [...current, index]) }}>
            <span className="eval-case-title"><b>Scenario {index + 1}</b><span>{test.name}</span></span>
            <span className="eval-case-preview">{Object.values(test.variables).find((value) => value.trim()) || 'Enter the inputs this prompt should handle.'}</span>
            <span className="eval-case-chevron" aria-hidden="true" />
          </summary>
          <div className="eval-case-body">
          <div className="eval-case-heading"><h3>Scenario {index + 1}</h3>{setup.cases.length > 1 && <button type="button" className="text-button" onClick={() => { setSetup({ ...setup, cases: setup.cases.filter((_, i) => i !== index) }); setExpandedCases((current) => current.filter((i) => i !== index).map((i) => i > index ? i - 1 : i)) }}>Remove scenario {index + 1}</button>}</div>
          <label className="field"><span>Scenario name {index + 1}</span><input maxLength={100} value={test.name} onChange={(event) => updateCase(index, { name: event.target.value })} placeholder="For example: A customer asks about a late delivery" /></label>
          {names.map((variable) => <label className="field" key={variable}><span>{variable.replace(/_/g, ' ')} · scenario {index + 1}</span><textarea maxLength={2000} value={test.variables[variable] ?? ''} onChange={(event) => updateCase(index, { variables: { ...test.variables, [variable]: event.target.value } })} placeholder={`Enter the ${variable.replace(/_/g, ' ')} for this scenario`} /></label>)}
          {!names.length && <p>This prompt does not need input details. You can still describe what a correct answer should say.</p>}
          <label className="field"><span>Expected answer · scenario {index + 1} (optional)</span><textarea maxLength={3000} value={test.reference} onChange={(event) => updateCase(index, { reference: event.target.value })} placeholder="Add verified facts or an answer you trust. Leave this blank if you do not have one." /></label>
        </div></details>)}
        <div className="eval-actions eval-example-tools"><Button secondary onClick={() => void action('Suggesting test cases', async () => {
          if (setup.version_ids.length < 2 || setup.version_ids.length > 5 || setup.goal.trim().length < 10) throw new Error('Choose two to five versions and describe your goal first.')
          setSuggestion(await evaluationApi.suggest(promptId, { version_ids: setup.version_ids, goal: setup.goal, preset: setup.preset }))
        })}>Suggest scenarios</Button><Button secondary onClick={() => void reuseRuns()}>Use inputs from past runs</Button></div>
        {suggestion && <section className="eval-suggestion" aria-label="Suggested setup"><h3>Review Gemini’s suggestions</h3><p>{suggestion.notes}</p>{suggestion.cases.map((test, index) => <details key={index}><summary>{test.name}</summary><ExampleInputs values={test.variables} /></details>)}<p>{metricNames.map((key) => `${metricLabel(key)} ${suggestion.weights[key]}%`).join(' · ')}</p><AnswerRules requirements={suggestion.requirements} /><p>Review these scenarios before using them. Add an expected answer only if you can verify it.</p><Button onClick={() => { setExpandedCases([0]); setSetup({ ...setup, cases: suggestion.cases, weights: suggestion.weights, requirements: suggestion.requirements }); setSuggestion(null); setNotice('Suggested scenarios and preferences added below. Review them before comparing.') }}>Use suggested scenarios and preferences</Button></section>}
      </fieldset>
      <fieldset id="eval-step-preferences" className="eval-step eval-preferences-step" disabled={active}><legend>3. Choose your answer preferences</legend>
        <p className="eval-muted eval-weight-intro">Set how each factor contributes to the final score. Total must be 100%.</p>
        <div className="eval-embedding-setting">
        <div className="eval-embedding-toggle"><span>Compare meaning with vector embeddings</span></div>
        <p className="eval-muted">When you add an expected answer, Gemini compares its meaning with each version’s answer.</p>
        </div>
        <div className="eval-weight-settings"><div className="eval-weights">{metricNames.map((metric) => <label className="field" key={metric}><span>{metricLabel(metric)} (%)</span><small className="eval-muted" id={`eval-metric-help-${metric}`}>{metricDefinitions[metric]}</small><div className="eval-percent-input"><input aria-label={`${metricLabel(metric)} (%)`} aria-describedby={`eval-metric-help-${metric}`} type="number" min={0} max={100} step={1} value={setup.weights[metric]} onChange={(event) => setSetup({ ...setup, weights: { ...setup.weights, [metric]: Number(event.target.value) } })} /><span aria-hidden="true">%</span></div></label>)}</div><div className="eval-scoring-notes"><p className="eval-total" role="status"><strong>Total priority: {Object.values(setup.weights).reduce((a, b) => a + b, 0)} / 100</strong> Higher percentages give a quality more influence on the result. If the top scores are within 3 points, we report a close result rather than pick a winner.</p><p>The suggested priorities are a starting point. You can leave them as they are or adjust them to suit your goal.</p><p>When you provide an expected answer, the final score combines 80% quality assessment and 20% meaning similarity (negative similarity counts as zero). Without one, only quality is scored. Similarity does not verify facts.</p></div></div>
        <p className="eval-muted">Keep answers short if your task needs it. Leave the limit empty for any length.</p><AnswerRules requirements={{ ...setup.requirements, max_words: null }} /><div className="eval-requirements">
          <label className="field"><span>Answer length limit (words, optional)</span><input type="number" min={1} max={10000} value={setup.requirements.max_words ?? ''} onChange={(event) => setSetup({ ...setup, requirements: { ...setup.requirements, max_words: event.target.value ? Number(event.target.value) : null } })} /></label>
        </div>

      </fieldset>
      <div className="eval-run-bar"><p>We’ll compare {setup.version_ids.length} versions using {setup.cases.length} {setup.cases.length === 1 ? 'scenario' : 'scenarios'} ({total} answers). A version must meet your answer preferences to be recommended. Your comparison is saved automatically.</p><div className="eval-actions"><Button secondary disabled={active} onClick={() => void action('Saving setup', async () => { validate(); await evaluationApi.saveSetup(promptId, normalizedSetup(setup)); setNotice('Evaluation setup saved.') })}>Save setup</Button><Button disabled={active || versions.length < 2} onClick={() => { setSetup(normalizedSetup(setup)); void start() }}>{busy || (running(evaluation) ? 'Comparing answers…' : 'Compare versions')}</Button></div></div>
    </section>}
    {evaluationId && !evaluation && <p role="status">Loading saved evaluation…</p>}
    {evaluation && <section className="eval-report" aria-label="Evaluation results" ref={reportRef} tabIndex={-1}>
      <div className="panel eval-result-head"><Status tone={evaluation.status === 'completed' ? 'success' : evaluation.status === 'failed' || evaluation.status === 'interrupted' ? 'warning' : 'neutral'}>{metricLabel(evaluation.status)}</Status><h2>{evaluation.winner_version_id ? `Recommended: ${label(evaluation.winner_version_id)}` : running(evaluation) ? 'Comparing your versions' : 'No winner selected'}</h2><p>{evaluation.recommendation || evaluation.error || 'Gemini is generating and assessing answers. You can return to this saved comparison later.'}</p><p role="status">{evaluation.results.filter((row) => row.weighted_score !== null || row.error).length} / {evaluation.configuration.version_ids.length * evaluation.configuration.cases.length} results processed · {new Date(evaluation.created_at).toLocaleString()}</p><p className="eval-muted">{evaluation.configuration.use_embeddings ? 'Embedding comparison enabled. Each answer shows the blend used when it was evaluated.' : 'Quality assessment only; embeddings were not enabled for this comparison.'}</p><p className="eval-muted">This recommendation is based on the scenarios in this comparison. Results can vary. Correctness is compared with an expected answer only when you provide one.</p><details className="eval-advanced"><summary>Your goal and comparison preferences</summary><p>{evaluation.configuration.goal}</p><p>{metricNames.map((metric) => `${metricLabel(metric)} ${evaluation.configuration.weights[metric]}%`).join(' · ')}</p><AnswerRules requirements={evaluation.configuration.requirements} /><Button secondary disabled={active} onClick={() => { setSetup({ ...structuredClone(evaluation.configuration), use_embeddings: true }); setNotice('Your saved preferences are ready to edit above.') }}>Use these preferences again</Button></details></div>
      <div className="eval-rankings">{evaluation.ranking.map((item) => <article className="panel eval-ranking" key={item.version_id}><h3>{label(item.version_id)}</h3><strong>{item.score === null ? 'Unscored' : `${item.score.toFixed(1)} / 100`}</strong><p>{item.reason}</p><small>{item.passed_cases}/{item.total_cases} scenarios met your answer preferences</small></article>)}</div>
      {evaluation.configuration.cases.map((test, index) => <section key={index} className="panel eval-case-results"><h3>{test.name}</h3><div className="eval-case-context" role="group" aria-label={`Saved scenario: ${test.name}`}><h4>Inputs used for this scenario</h4><ExampleInputs values={test.variables} /><h4>Expected answer</h4><p>{test.reference || 'No expected answer was provided, so factual accuracy has not been verified.'}</p></div><div className="eval-output-grid">{evaluation.configuration.version_ids.map((id) => {
        const result = evaluation.results.find((row) => row.case_index === index && row.version_id === id)
        return <article key={id} className="eval-output"><h4>{label(id)} · {result?.weighted_score == null ? 'Unscored' : `${result.weighted_score} / 100`}</h4>{!result ? <p>Awaiting generation</p> : <><p>{result.error || result.summary || 'Awaiting assessment'}</p>{result.checks.map((check) => <p className={check.passed ? 'eval-pass' : 'eval-fail'} key={check.name}>{check.passed ? '✓' : '✕'} {checkDescription(check)}</p>)}<pre>{result.output || 'No output available'}</pre>{evaluation.configuration.use_embeddings && <p className="eval-muted">{result.embedding ? `Cosine similarity: ${result.embedding.cosine_similarity.toFixed(4)} · Blend: ${Math.round((1 - (result.embedding.similarity_weight ?? 0.3)) * 100)}% quality / ${Math.round((result.embedding.similarity_weight ?? 0.3) * 100)}% similarity · Quality: ${result.embedding.quality_score.toFixed(1)} / 100 · Final: ${result.weighted_score?.toFixed(1)} / 100 · ${result.embedding.model}` : test.reference ? 'Embedding comparison not completed.' : 'No expected answer: quality-only score.'}</p>}{Object.entries(result.scores).map(([metric, score]) => <details key={metric}><summary>{metricLabel(metric)}: {score!.score} / 5</summary><p>{score!.reason}</p><blockquote><mark>{score!.evidence}</mark></blockquote></details>)}</> }</article>
      })}</div></section>)}
      {evaluation.status === 'completed' && <section className="panel eval-improve"><h3>Build on what you learned</h3><p>Use what you learned to improve a version. Review the draft, save it as a new version, and compare it again before requesting approval to use it.</p><div className="eval-actions"><label className="field"><span>Version to improve</span><select disabled={Boolean(busy)} value={improveId} onChange={(event) => { setImproveId(event.target.value); setDraft(null) }}>{evaluation.configuration.version_ids.map((id) => <option key={id} value={id}>{label(id)}</option>)}</select></label><Button secondary disabled={Boolean(busy)} onClick={() => void action('Drafting improvement', async () => { const suggested = await evaluationApi.improve(promptId, evaluation.id, improveId); setDraft({ ...suggested, versionId: improveId, evaluationId: evaluation.id }) })}>Suggest an improvement</Button></div>{draft && <><p>{draft.explanation}</p><label className="field"><span>Review and edit the suggested template</span><textarea className="eval-draft" maxLength={100000} value={draft.template} onChange={(event) => setDraft({ ...draft, template: event.target.value })} disabled={Boolean(busy)} /></label><label className="field"><span>What changed?</span><input value={commit} maxLength={500} onChange={(event) => setCommit(event.target.value)} disabled={Boolean(busy)} /></label><Button disabled={Boolean(busy)} onClick={() => void action('Saving improved version', async () => {
          if (!draft.template.trim() || !commit.trim()) throw new Error('Add a template and commit message before saving.')
          const base = evaluation.version_snapshots.find((v) => v.id === draft.versionId)
          if (!base) throw new Error('The evaluated base version could not be found.')
          const created = await workspaceService.createVersion(promptId, { parent_version_id: base.id, template: draft.template, model_config: base.model_config, commit_message: commit.trim() })
          setDraft(null); refreshLiveData(); setNotice(`Saved v${created.version_number}. Select it above and evaluate it before requesting activation.`)
        })}>Save as a new version</Button></>}</section>}
    </section>}
    <section className="panel eval-history"><h2>Evaluation history</h2>{history.length ? <table className="eval-history-table"><thead><tr><th scope="col">Date</th><th scope="col">Status</th><th scope="col">Recommendation</th></tr></thead><tbody>{history.map((item) => <tr key={item.id}><td data-label="Date">{new Date(item.created_at).toLocaleString()}</td><td data-label="Status">{metricLabel(item.status)} · {item.completed_cases}/{item.total_cases} results recorded</td><td data-label="Recommendation"><button type="button" className="eval-history-open" onClick={() => { setQuery({ evaluation: item.id }); setError('') }}>{item.recommendation || item.error || 'View progress'}</button></td></tr>)}</tbody></table> : <p>Your saved comparisons will appear here.</p>}</section>
  </div>
}

function normalizedSetup(setup: Setup): Setup {
  return { ...setup, use_embeddings: true, requirements: { ...setup.requirements, required_fields: setup.requirements.required_fields.map((field) => field.trim()).filter(Boolean) } }
}
