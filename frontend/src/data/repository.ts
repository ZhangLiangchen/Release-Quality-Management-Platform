import type {
  AutomationFramework,
  AutomationRun,
  CaseDetail,
  CicdPipeline,
  CicdRun,
  CloseIssuePayload,
  CreateIssuePayload,
  DashboardKpi,
  ImportValidationResult,
  Issue,
  IssueQuery,
  LoginPayload,
  LoginResult,
  ModuleCaseGroup,
  ProjectConfig,
  SaveAutomationConfigurationPayload,
  SaveAutomationTestSuitePayload,
  UpdateCaseStatusPayload,
  UpdateCicdStagePayload,
  TriggerAutomationRunPayload,
  User,
  Version,
  TriggerCicdRunPayload,
} from '../domain/types';

export interface Repository {
  login(payload: LoginPayload): Promise<LoginResult>;
  getCurrentUser(token: string): Promise<User>;

  getConfig(): Promise<ProjectConfig>;
  updateConfig(projectName: string): Promise<ProjectConfig>;

  listVersions(): Promise<Version[]>;
  createVersion(versionKey: string): Promise<Version>;
  setCurrentVersion(versionKey: string): Promise<void>;
  deleteVersion(versionKey: string): Promise<void>;

  listUsers(): Promise<User[]>;
  createUser(payload: Pick<User, 'username' | 'email' | 'role'>): Promise<User>;
  deleteUser(userId: string): Promise<void>;

  listCases(versionKey: string): Promise<ModuleCaseGroup[]>;
  getCaseDetail(versionKey: string, caseKey: string): Promise<CaseDetail>;
  updateCaseStatus(payload: UpdateCaseStatusPayload, operator: User): Promise<void>;

  listIssues(query: IssueQuery): Promise<Issue[]>;
  createIssue(payload: CreateIssuePayload): Promise<Issue>;
  updateIssue(issueKey: string, patch: Partial<Pick<Issue, 'title' | 'description' | 'priority' | 'assigneeId'>>): Promise<Issue>;
  transitionIssue(issueKey: string, nextStatus: Issue['status']): Promise<Issue>;
  closeIssue(issueKey: string, payload: CloseIssuePayload): Promise<Issue>;

  getDashboard(versionKey: string): Promise<DashboardKpi>;
  listPendingIssues(versionKey: string): Promise<Issue[]>;

  downloadTemplate(kind: 'cases' | 'issues', format: 'csv' | 'xlsx'): Promise<Blob>;
  validateImport(kind: 'cases' | 'issues', file: File): Promise<ImportValidationResult>;
  exportData(kind: 'cases' | 'issues', format: 'csv' | 'xlsx', versionKey: string): Promise<Blob>;

  getCicdPipeline(pipelineKey: string): Promise<CicdPipeline>;
  listCicdRuns(pipelineKey: string): Promise<CicdRun[]>;
  triggerCicdRun(payload: TriggerCicdRunPayload): Promise<CicdRun>;
  updateCicdStage(payload: UpdateCicdStagePayload): Promise<CicdRun>;

  getAutomationFramework(frameworkKey: string): Promise<AutomationFramework>;
  listAutomationRuns(frameworkKey: string): Promise<AutomationRun[]>;
  saveAutomationConfiguration(payload: SaveAutomationConfigurationPayload): Promise<AutomationFramework>;
  saveAutomationTestSuite(payload: SaveAutomationTestSuitePayload): Promise<AutomationFramework>;
  triggerAutomationRun(payload: TriggerAutomationRunPayload): Promise<AutomationRun>;
}
