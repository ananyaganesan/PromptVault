import { Status } from '../../components/ui/prototype'
import { metricLabel } from '../evaluations/evaluation-api'
import type { ReleaseValidation } from './release-validation-api'

export function ReleaseValidationPanel({ report, historical = false }: { report: ReleaseValidation | null | undefined; historical?: boolean }) {
  if (!report) return <section className="panel release-validation"><h2>Release validation</h2><p>{historical ? 'No validation report was recorded for this historical release.' : 'No validation report is attached. The requester must validate this release before approval.'}</p></section>
  const recorded = historical && report.status === 'stale'
  const running = report.status === 'queued' || report.status === 'running'
  return <section className="panel release-validation" aria-label="Release validation evidence">
    <div className="panel-head"><div><h2>Release validation</h2><p>{recorded ? 'Recorded evidence for this release. A future release needs fresh validation.' : report.summary}</p></div><Status tone={report.status === 'passed' ? 'success' : 'warning'}>{recorded ? 'Recorded' : report.status}</Status></div>
    <p className="deployment-hint">Checked {new Date(report.created_at).toLocaleString()} · Every test needs {report.minimum_score}/100 and all required checks. Evidence expires after 24 hours.</p>
    {report.checks.map((check) => <div className="health-row" key={check.name}><div><b>{check.name}</b><p>{check.detail}</p></div><Status tone={check.passed ? 'success' : 'warning'}>{check.passed ? 'Passed' : 'Failed'}</Status></div>)}
    {report.configuration && <details className="release-test-result"><summary>Test suite used</summary><p>{report.configuration.goal}</p><p>Metric weights: {Object.entries(report.configuration.weights).map(([metric, weight]) => `${metricLabel(metric)} ${weight}%`).join(' · ')}</p><p>Requirements: {report.configuration.requirements.max_words ? `Maximum ${report.configuration.requirements.max_words} words. ` : ''}{report.configuration.requirements.valid_json ? `Valid JSON${report.configuration.requirements.required_fields.length ? ` with fields: ${report.configuration.requirements.required_fields.join(', ')}` : ''}.` : 'No JSON format requirement.'}</p>{report.configuration.cases.map((testCase, index) => <div key={index}><b>{testCase.name}</b><pre>{JSON.stringify(testCase.variables, null, 2)}</pre>{testCase.reference && <p>Expected answer: {testCase.reference}</p>}</div>)}</details>}
    {running && <p role="status">Running Gemini tests… You can refresh this page without losing progress.</p>}
    {report.evaluation?.error && <p role="alert">{report.evaluation.error}</p>}
    {report.evaluation?.results.map((result) => <details className="release-test-result" key={result.case_index}>
      <summary>{report.configuration?.cases[result.case_index]?.name ?? `Test ${result.case_index + 1}`} · {result.weighted_score === null ? 'Unscored' : `${result.weighted_score}/100`}{result.error || result.checks.some((check) => !check.passed) || (result.weighted_score !== null && result.weighted_score < report.minimum_score) ? ' · Failed' : ''}</summary>
      {result.error && <p role="alert">{result.error}</p>}
      {result.checks.map((check) => <p key={check.name}>{check.passed ? 'Passed' : 'Failed'}: {check.name} — {check.detail}</p>)}
      <pre>{result.output || 'No output recorded.'}</pre>
      {Object.entries(result.scores).map(([metric, score]) => score && <p key={metric}><b>{metricLabel(metric)}: {score.score}/5</b> — {score.reason}<br /><q>{score.evidence}</q></p>)}
      <p>{result.summary}</p>
    </details>)}
  </section>
}
