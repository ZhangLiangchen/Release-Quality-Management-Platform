export type UserRole = 'admin' | 'qa' | 'dev' | 'viewer';

export type CaseStatus = 'not_run' | 'passed' | 'failed' | 'blocked' | 'skipped';

export type IssueStatus =
  | 'new'
  | 'assigned'
  | 'fixing'
  | 'to_verify'
  | 'verify_failed'
  | 'closed'
  | 'rejected'
  | 'duplicate'
  | 'invalid'
  | 'deferred';

export type IssueStatusGroup = 'all' | 'open' | 'pending' | 'closed' | 'invalid';

export type IssuePriority = 'high' | 'medium' | 'low';

export type IssueSeverity = 'critical' | 'major' | 'minor';

export type CaseLinkType = 'repro' | 'regression';

export interface User {
  userId: string;
  username: string;
  email: string;
  role: UserRole;
  status: 'active' | 'disabled';
}

export interface Version {
  versionId: string;
  versionKey: string;
  name: string;
  isCurrent: boolean;
  createdAt: string;
}

export interface ProjectConfig {
  projectName: string;
  currentVersionKey: string;
}

export interface FileAttachment {
  name: string;
  url: string;
  size?: number;
  mime?: string;
}

export interface TestCase {
  caseId: string;
  caseKey: string;
  title: string;
  steps: string;
  expected: string;
  module: string;
  tags: string[];
  status: 'active' | 'deprecated';
}

export interface CaseWithStatus extends TestCase {
  latestStatus: CaseStatus;
  latestUpdatedAt?: string;
  latestUpdatedBy?: string;
}

export interface ModuleCaseGroup {
  module: string;
  cases: CaseWithStatus[];
}

export interface CaseExecutionHistory {
  id: string;
  versionKey: string;
  caseKey: string;
  status: CaseStatus;
  executorId: string;
  executorName: string;
  executedAt: string;
  note?: string;
  attachments: FileAttachment[];
}

export interface CaseDetail {
  caseInfo: CaseWithStatus;
  history: CaseExecutionHistory[];
}

export interface IssueCaseLink {
  caseKey: string;
  linkType: CaseLinkType;
  note?: string;
}

export interface Issue {
  issueId: string;
  issueKey: string;
  title: string;
  description: string;
  status: IssueStatus;
  priority: IssuePriority;
  severity: IssueSeverity;
  assigneeId?: string;
  assigneeName?: string;
  reporterId: string;
  reporterName: string;
  foundVersionKey: string;
  fixVersionKey?: string;
  verifyVersionKey?: string;
  createdAt: string;
  updatedAt: string;
  links: IssueCaseLink[];
}

export interface DashboardKpi {
  totalCases: number;
  executedCases: number;
  passedCases: number;
  skippedCases: number;
  executionRate: number;
  passRate: number | null;
  totalIssues: number;
  resolvedIssues: number;
  resolutionRate: number;
  pendingIssueCount: number;
}

export interface LoginPayload {
  username: string;
  password: string;
}

export interface LoginResult {
  accessToken: string;
  user: User;
}

export interface UpdateCaseStatusPayload {
  versionKey: string;
  caseKey: string;
  status: CaseStatus;
  note?: string;
  attachments?: FileAttachment[];
}

export interface CreateIssuePayload {
  title: string;
  description: string;
  priority: IssuePriority;
  severity: IssueSeverity;
  assigneeId?: string;
  reporterId: string;
  foundVersionKey: string;
  links: IssueCaseLink[];
}

export interface CloseIssuePayload {
  fixVersionKey: string;
  verifyVersionKey: string;
  regressionCaseKeys: string[];
}

export interface IssueQuery {
  versionKey: string;
  statusGroup: IssueStatusGroup;
  assigneeId?: string;
}

export interface ImportValidationResult {
  kind: 'cases' | 'issues';
  totalRows: number;
  validRows: number;
  errors: string[];
  preview: Record<string, string>[];
}

export type CicdStageStatus = 'pending' | 'running' | 'success' | 'failed';
export type CicdRunStatus = 'pending' | 'running' | 'success' | 'failed';

export interface CicdHost {
  name: string;
  ip: string;
  note: string;
}

export interface CicdStage {
  stageKey: string;
  name: string;
  description: string;
  command: string;
  status: CicdStageStatus;
  updatedAt?: string;
  note?: string;
}

export interface CicdPipeline {
  pipelineKey: string;
  pipelineName: string;
  projectName: string;
  binaryName: string;
  buildMachine: CicdHost;
  deployTarget: CicdHost;
  buildScriptPath: string;
  artifactPath: string;
  deployPath: string;
  stagesTemplate: Omit<CicdStage, 'status' | 'updatedAt' | 'note'>[];
  updatedAt: string;
}

export interface CicdRun {
  runId: string;
  pipelineKey: string;
  pipelineName: string;
  branch: string;
  commitId?: string;
  note?: string;
  status: CicdRunStatus;
  triggeredBy: string;
  startedAt: string;
  finishedAt?: string;
  stages: CicdStage[];
  logs: string[];
}

export interface TriggerCicdRunPayload {
  pipelineKey: string;
  branch: string;
  commitId?: string;
  note?: string;
  triggeredBy: string;
}

export interface UpdateCicdStagePayload {
  runId: string;
  stageKey: string;
  status: CicdStageStatus;
  note?: string;
}

export type AutomationFrameworkKey = 'frigateDynamic' | 'hypersonic';
export type AutomationFrameworkType = 'performance' | 'functional';
export type AutomationRunStatus = 'pending' | 'running' | 'success' | 'failed';
export type AutomationOperationMode =
  | 'deploy_pressure_machine'
  | 'deploy_hyperchain'
  | 'deploy_and_test'
  | 'test_only'
  | 'functional_test';

export interface AutomationConfiguration {
  configKey: string;
  name: string;
  description: string;
  content: string;
  updatedAt: string;
  updatedBy: string;
}

export interface AutomationTestSuite {
  suiteKey: string;
  name: string;
  description: string;
  content: string;
  updatedAt: string;
  updatedBy: string;
}

export interface AutomationOperationOption {
  mode: AutomationOperationMode;
  label: string;
  description: string;
}

export interface AutomationFramework {
  frameworkKey: AutomationFrameworkKey;
  entryName: string;
  displayName: string;
  frameworkType: AutomationFrameworkType;
  description: string;
  streamlitUrl?: string;
  buildMachine: CicdHost;
  deployTarget: CicdHost;
  configurations: AutomationConfiguration[];
  testSuites: AutomationTestSuite[];
  operationModes: AutomationOperationOption[];
  updatedAt: string;
}

export interface AutomationRun {
  runId: string;
  frameworkKey: AutomationFrameworkKey;
  entryName: string;
  configurationKey: string;
  testSuiteKey: string;
  operationMode: AutomationOperationMode;
  status: AutomationRunStatus;
  note?: string;
  triggeredBy: string;
  startedAt: string;
  finishedAt?: string;
  logs: string[];
}

export interface SaveAutomationConfigurationPayload {
  frameworkKey: AutomationFrameworkKey;
  configKey: string;
  content: string;
  updatedBy: string;
}

export interface SaveAutomationTestSuitePayload {
  frameworkKey: AutomationFrameworkKey;
  suiteKey: string;
  content: string;
  updatedBy: string;
}

export interface TriggerAutomationRunPayload {
  frameworkKey: AutomationFrameworkKey;
  configurationKey: string;
  testSuiteKey: string;
  operationMode: AutomationOperationMode;
  note?: string;
  triggeredBy: string;
}
