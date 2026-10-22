import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from '../components/layout/app-layout'
import { AuthLayout } from '../components/layout/auth-layout'
import { ProviderKeyManagementPage, UserManagementPage } from '../features/admin/console-pages'
import { AuditLogPage } from '../features/admin/governance-console'
import { DeploymentApprovalQueuePage, DeploymentApprovalReviewPage, DeploymentRollbackPage } from '../features/admin/deployment-governance'
import { AdminOnly } from '../features/admin/admin-only'
import { ApiTokensPage, ProfilePage } from '../features/account/account-pages'
import { ForgotPasswordPage, LoginPage, RegisterPage, ResetPasswordPage, VerifyEmailPage } from '../features/auth/pages'
import { AuthProvider } from '../features/auth/auth-context'
import { RequireAuth } from '../features/auth/guards'
import { DashboardPage } from '../features/dashboard/dashboard-page'
import { DeploymentDetailPage, DeploymentListPage, NewDeploymentPage } from '../features/deployments/deployment-pages'
import { PlaygroundPage } from '../features/playground/playground-page'
import { NewProjectPage, ProjectDetailPage, ProjectsPage } from '../features/projects/project-pages'
import { ProjectInvitationPage } from '../features/projects/invitation-page'
import { WorkspaceBoundary } from '../features/projects/workspace-boundary'
import { NewPromptPage, PromptDetailPage, PromptsPage } from '../features/prompts/prompt-pages'
import { CompareVersionPage, VersionDetailPage, VersionLineagePage } from '../features/versions/version-pages'
import { ErrorPage } from '../features/workspace/error-page'

export function App() {
  return <AuthProvider><BrowserRouter><Routes>
    <Route path="/" element={<Navigate to="/login" replace />} />
    <Route element={<AuthLayout />}>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/403" element={<ErrorPage code="403" />} />
      <Route path="/404" element={<ErrorPage code="404" />} />
    </Route>
    <Route element={<RequireAuth />}>
      <Route path="/project-invitations" element={<ProjectInvitationPage />} />
    </Route>
    <Route element={<RequireAuth />}><Route element={<WorkspaceBoundary />}><Route element={<AppLayout />}>
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/projects" element={<ProjectsPage />} />
      <Route element={<AdminOnly />}>
        <Route path="/projects/new" element={<NewProjectPage />} />
      </Route>
      <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
      <Route path="/prompts" element={<PromptsPage />} />
      <Route path="/prompts/new" element={<NewPromptPage />} />
      <Route path="/prompts/:promptId" element={<PromptDetailPage />} />
      <Route path="/versions/:versionId" element={<VersionDetailPage />} />
      <Route path="/versions/:versionId/compare" element={<CompareVersionPage />} />
      <Route path="/versions/:versionId/lineage" element={<VersionLineagePage />} />
      <Route path="/playground" element={<PlaygroundPage />} />
      <Route path="/deployments" element={<DeploymentListPage />} />
      <Route path="/deployments/new" element={<NewDeploymentPage />} />
      <Route path="/deployments/:deploymentId" element={<DeploymentDetailPage />} />
      <Route path="/api-tokens" element={<ApiTokensPage />} />
      <Route path="/profile" element={<ProfilePage />} />
      <Route element={<AdminOnly />}>
      <Route path="/admin/approvals" element={<DeploymentApprovalQueuePage />} />
      <Route path="/admin/approvals/:approvalId" element={<DeploymentApprovalReviewPage />} />
      <Route path="/admin/rollback" element={<DeploymentRollbackPage />} />
      <Route path="/admin/users" element={<UserManagementPage />} />
      <Route path="/admin/provider-keys" element={<ProviderKeyManagementPage />} />
      <Route path="/admin/audit" element={<AuditLogPage />} />
      </Route>
    </Route></Route></Route>
    <Route path="*" element={<Navigate to="/404" replace />} />
  </Routes></BrowserRouter></AuthProvider>
}
