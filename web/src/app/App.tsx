import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from '../components/layout/app-layout'
import { AuthLayout } from '../components/layout/auth-layout'
import { AdminPage, ApprovalPage, ProviderKeysPage, UsersPage } from '../features/admin/admin-pages'
import { AdminRunsPage, ApprovalDetailPage, AuditPage, BudgetsPage, MaintenancePage, ModelPricingPage, RollbackPage } from '../features/admin/governance-pages'
import { ApiTokensPage, CostsPage, ProfilePage } from '../features/account/account-pages'
import { ForgotPasswordPage, LoginPage, RegisterPage } from '../features/auth/pages'
import { DashboardPage } from '../features/dashboard/dashboard-page'
import { DeploymentDetailPage, DeploymentListPage, NewDeploymentPage } from '../features/deployments/deployment-pages'
import { PlaygroundPage } from '../features/playground/playground-page'
import { NewProjectPage, ProjectDetailPage, ProjectsPage } from '../features/projects/project-pages'
import { NewPromptPage, PromptDetailPage, PromptsPage } from '../features/prompts/prompt-pages'
import { RunsPage } from '../features/runs/runs-page'
import { CompareVersionPage, VersionDetailPage, VersionLineagePage } from '../features/versions/version-pages'
import { ErrorPage } from '../features/workspace/error-page'

export function App() {
  return <BrowserRouter><Routes>
    <Route path="/" element={<Navigate to="/login" replace />} />
    <Route element={<AuthLayout />}>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/403" element={<ErrorPage code="403" />} />
      <Route path="/404" element={<ErrorPage code="404" />} />
    </Route>
    <Route element={<AppLayout />}>
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/projects" element={<ProjectsPage />} />
      <Route path="/projects/new" element={<NewProjectPage />} />
      <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
      <Route path="/prompts" element={<PromptsPage />} />
      <Route path="/prompts/new" element={<NewPromptPage />} />
      <Route path="/prompts/:promptId" element={<PromptDetailPage />} />
      <Route path="/versions/:versionId" element={<VersionDetailPage />} />
      <Route path="/versions/:versionId/compare" element={<CompareVersionPage />} />
      <Route path="/versions/:versionId/lineage" element={<VersionLineagePage />} />
      <Route path="/playground" element={<PlaygroundPage />} />
      <Route path="/runs" element={<RunsPage />} />
      <Route path="/deployments" element={<DeploymentListPage />} />
      <Route path="/deployments/new" element={<NewDeploymentPage />} />
      <Route path="/deployments/:deploymentId" element={<DeploymentDetailPage />} />
      <Route path="/costs" element={<CostsPage />} />
      <Route path="/api-tokens" element={<ApiTokensPage />} />
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="/admin/approvals" element={<ApprovalPage />} />
      <Route path="/admin/approvals/:approvalId" element={<ApprovalDetailPage />} />
      <Route path="/admin/rollback" element={<RollbackPage />} />
      <Route path="/admin/users" element={<UsersPage />} />
      <Route path="/admin/provider-keys" element={<ProviderKeysPage />} />
      <Route path="/admin/budgets" element={<BudgetsPage />} />
      <Route path="/admin/runs" element={<AdminRunsPage />} />
      <Route path="/admin/audit" element={<AuditPage />} />
      <Route path="/admin/model-pricing" element={<ModelPricingPage />} />
      <Route path="/admin/maintenance" element={<MaintenancePage />} />
    </Route>
    <Route path="*" element={<Navigate to="/404" replace />} />
  </Routes></BrowserRouter>
}
