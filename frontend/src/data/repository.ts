import type {
  AutomationFramework,
  AutomationRun,
  AutomationRunLogChunk,
  CaseTreeNode,
  CreatePlanPayload,
  CreateRunPayload,
  CreateSuitePayload,
  UpdateSuitePayload,
  CreateCasePayload,
  UpdateCasePayload,
  CreateCaseTreeNodePayload,
  CaseDetail,
  CicdRunLogChunk,
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
  Plan,
  ProjectConfig,
  Run,
  RunCase,
  RunCaseHistory,
  SaveAutomationConfigurationPayload,
  SaveAutomationTestSuitePayload,
  Suite,
  SuiteVersion,
  SuiteVersionDetail,
  UpdateCaseStatusPayload,
  UpdateRunCaseStatusPayload,
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
  listCaseTree(versionKey: string): Promise<CaseTreeNode[]>;
  createCaseTreeNode(payload: CreateCaseTreeNodePayload): Promise<CaseTreeNode>;
  createCase(payload: CreateCasePayload): Promise<void>;
  updateCase(payload: UpdateCasePayload): Promise<void>;
  deleteCase(caseKey: string): Promise<void>;
  getCaseDetail(versionKey: string, caseKey: string): Promise<CaseDetail>;
  updateCaseStatus(payload: UpdateCaseStatusPayload, operator: User): Promise<void>;

  listSuites(versionKey: string): Promise<Suite[]>;
  createSuite(payload: CreateSuitePayload): Promise<Suite>;
  updateSuite(payload: UpdateSuitePayload): Promise<Suite>;
  deleteSuite(suiteKey: string, suiteVersionKey: string): Promise<void>;
  getSuiteVersionDetail(suiteKey: string, suiteVersionKey: string): Promise<SuiteVersionDetail>;
  deriveSuiteVersion(suiteKey: string, note?: string): Promise<SuiteVersion>;
  publishSuiteVersion(suiteKey: string, suiteVersionKey: string): Promise<SuiteVersion>;
  addSuiteCases(suiteKey: string, suiteVersionKey: string, caseKeys: string[]): Promise<void>;
  removeSuiteCases(suiteKey: string, suiteVersionKey: string, caseKeys: string[]): Promise<void>;

  listPlans(versionKey: string): Promise<Plan[]>;
  createPlan(payload: CreatePlanPayload): Promise<Plan>;
  deletePlan(planKey: string): Promise<void>;
  getPlanDetail(planKey: string): Promise<{ plan: Plan; runs: Run[] }>;
  createRun(planKey: string, payload: CreateRunPayload): Promise<Run>;

  listRuns(versionKey: string): Promise<Run[]>;
  getLatestRun(versionKey: string): Promise<Run>;
  getRunDetail(runKey: string): Promise<Run>;
  listRunCases(runKey: string, status?: RunCase['status'], keyword?: string): Promise<RunCase[]>;
  updateRunCaseStatus(payload: UpdateRunCaseStatusPayload): Promise<void>;
  listRunCaseHistory(runKey: string, runCaseKey: string): Promise<RunCaseHistory[]>;

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
  getCicdRunLogs(runId: string, cursor: number, limit?: number): Promise<CicdRunLogChunk>;

  getAutomationFramework(frameworkKey: string): Promise<AutomationFramework>;
  listAutomationRuns(frameworkKey: string): Promise<AutomationRun[]>;
  getAutomationRunLogs(runId: string, cursor: number, limit?: number): Promise<AutomationRunLogChunk>;
  cancelAutomationRun(runId: string): Promise<AutomationRun>;
  saveAutomationConfiguration(payload: SaveAutomationConfigurationPayload): Promise<AutomationFramework>;
  saveAutomationTestSuite(payload: SaveAutomationTestSuitePayload): Promise<AutomationFramework>;
  triggerAutomationRun(payload: TriggerAutomationRunPayload): Promise<AutomationRun>;
}
