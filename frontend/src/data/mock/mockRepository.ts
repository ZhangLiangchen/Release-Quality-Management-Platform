import Papa from 'papaparse';
import * as XLSX from 'xlsx';
import { getIssueStatusGroup, statusMatchesGroup } from '../../domain/status';
import type {
  AutomationFramework,
  AutomationRun,
  AutomationRunStatus,
  AutomationOperationMode,
  CaseDetail,
  CaseWithStatus,
  CicdPipeline,
  CicdRun,
  CicdStage,
  CicdStageStatus,
  CloseIssuePayload,
  CreateIssuePayload,
  ImportValidationResult,
  Issue,
  IssueQuery,
  LoginPayload,
  LoginResult,
  ModuleCaseGroup,
  ProjectConfig,
  SaveAutomationConfigurationPayload,
  SaveAutomationTestSuitePayload,
  TriggerAutomationRunPayload,
  TriggerCicdRunPayload,
  UpdateCaseStatusPayload,
  UpdateCicdStagePayload,
  User,
  Version,
} from '../../domain/types';
import { calculateDashboardKpi } from '../../utils/metrics';
import type { Repository } from '../repository';
import { createInitialMockDatabase, type MockDatabase } from './data';

const DEFAULT_PASSWORD = 'password123';

export class MockRepositoryError extends Error {
  public readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function toModuleGroups(cases: CaseWithStatus[]): ModuleCaseGroup[] {
  const grouped = new Map<string, CaseWithStatus[]>();
  cases.forEach((item) => {
    const list = grouped.get(item.module) ?? [];
    list.push(item);
    grouped.set(item.module, list);
  });

  return Array.from(grouped.entries())
    .sort(([a], [b]) => a.localeCompare(b, 'zh-Hans-CN'))
    .map(([module, moduleCases]) => ({
      module,
      cases: moduleCases.sort((a, b) => a.caseKey.localeCompare(b.caseKey, 'en-US')),
    }));
}

function parseRowsFromCsv(text: string): Record<string, string>[] {
  const result = Papa.parse<Record<string, string>>(text, {
    header: true,
    skipEmptyLines: true,
    transformHeader: (header) => header.trim(),
  });

  if (result.errors.length > 0) {
    throw new MockRepositoryError('INVALID_FILE', `CSV 解析失败: ${result.errors[0].message}`);
  }

  return result.data.map((row) => {
    const normalized: Record<string, string> = {};
    Object.entries(row).forEach(([key, value]) => {
      normalized[key] = String(value ?? '').trim();
    });
    return normalized;
  });
}

function buildWorkbookBlob(rows: Record<string, string>[], format: 'csv' | 'xlsx'): Blob {
  if (format === 'csv') {
    const csv = Papa.unparse(rows);
    return new Blob([csv], { type: 'text/csv;charset=utf-8' });
  }

  const worksheet = XLSX.utils.json_to_sheet(rows);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, 'Sheet1');
  const buffer = XLSX.write(workbook, { type: 'array', bookType: 'xlsx' });
  return new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

async function parseRowsFromFile(file: File): Promise<Record<string, string>[]> {
  const lowerName = file.name.toLowerCase();

  if (lowerName.endsWith('.csv')) {
    const text = await file.text();
    return parseRowsFromCsv(text);
  }

  if (lowerName.endsWith('.xlsx')) {
    const buffer = await file.arrayBuffer();
    const workbook = XLSX.read(buffer, { type: 'array' });
    const firstSheetName = workbook.SheetNames[0];
    if (!firstSheetName) {
      throw new MockRepositoryError('INVALID_FILE', 'XLSX 文件为空');
    }
    const worksheet = workbook.Sheets[firstSheetName];
    const rows = XLSX.utils.sheet_to_json<Record<string, string>>(worksheet, {
      defval: '',
    });
    return rows.map((row) => {
      const normalized: Record<string, string> = {};
      Object.entries(row).forEach(([key, value]) => {
        normalized[String(key).trim()] = String(value ?? '').trim();
      });
      return normalized;
    });
  }

  throw new MockRepositoryError('INVALID_FILE', '仅支持 CSV 或 XLSX 文件');
}

export class MockRepository implements Repository {
  private state: MockDatabase;

  constructor(initialState?: MockDatabase) {
    this.state = deepClone(initialState ?? createInitialMockDatabase());
  }

  private findUserById(userId: string): User {
    const user = this.state.users.find((item) => item.userId === userId && item.status === 'active');
    if (!user) {
      throw new MockRepositoryError('NOT_FOUND', '用户不存在');
    }
    return user;
  }

  private getVersion(versionKey: string): Version {
    const version = this.state.versions.find((item) => item.versionKey === versionKey);
    if (!version) {
      throw new MockRepositoryError('NOT_FOUND', `版本 ${versionKey} 不存在`);
    }
    return version;
  }

  private getIssue(issueKey: string): Issue {
    const issue = this.state.issues.find((item) => item.issueKey === issueKey);
    if (!issue) {
      throw new MockRepositoryError('NOT_FOUND', `问题单 ${issueKey} 不存在`);
    }
    return issue;
  }

  private getCicdRun(runId: string): CicdRun {
    const run = this.state.cicdRuns.find((item) => item.runId === runId);
    if (!run) {
      throw new MockRepositoryError('NOT_FOUND', `流水线运行记录不存在: ${runId}`);
    }
    return run;
  }

  private getAutomationFrameworkState(frameworkKey: string): AutomationFramework {
    const framework = this.state.automationFrameworks.find((item) => item.frameworkKey === frameworkKey);
    if (!framework) {
      throw new MockRepositoryError('NOT_FOUND', `自动化框架不存在: ${frameworkKey}`);
    }
    return framework;
  }

  private buildCaseWithStatus(versionKey: string): CaseWithStatus[] {
    const statuses = this.state.versionCaseStatus[versionKey] ?? {};
    return this.state.cases
      .filter((item) => item.status === 'active')
      .map((item) => {
        const history = this.state.caseHistory
          .filter((entry) => entry.versionKey === versionKey && entry.caseKey === item.caseKey)
          .sort((a, b) => b.executedAt.localeCompare(a.executedAt));

        return {
          ...item,
          latestStatus: statuses[item.caseKey] ?? 'not_run',
          latestUpdatedAt: history[0]?.executedAt,
          latestUpdatedBy: history[0]?.executorName,
        };
      });
  }

  async login(payload: LoginPayload): Promise<LoginResult> {
    const user = this.state.users.find((item) => item.username === payload.username && item.status === 'active');

    if (!user || payload.password !== DEFAULT_PASSWORD) {
      throw new MockRepositoryError('UNAUTHORIZED', '用户名或密码错误');
    }

    return {
      accessToken: `mock-token-${user.userId}`,
      user: deepClone(user),
    };
  }

  async getCurrentUser(token: string): Promise<User> {
    const userId = token.replace('mock-token-', '');
    return deepClone(this.findUserById(userId));
  }

  async getConfig(): Promise<ProjectConfig> {
    return deepClone(this.state.config);
  }

  async updateConfig(projectName: string): Promise<ProjectConfig> {
    this.state.config.projectName = projectName;
    return deepClone(this.state.config);
  }

  async listVersions(): Promise<Version[]> {
    return deepClone(
      this.state.versions.sort((a, b) => a.createdAt.localeCompare(b.createdAt)).map((item) => ({ ...item })),
    );
  }

  async createVersion(versionKey: string): Promise<Version> {
    const normalized = versionKey.trim();
    if (!normalized) {
      throw new MockRepositoryError('VALIDATION_ERROR', '版本号不能为空');
    }
    if (this.state.versions.some((item) => item.versionKey === normalized)) {
      throw new MockRepositoryError('VALIDATION_ERROR', '版本号已存在');
    }

    const version: Version = {
      versionId: `V-${String(this.state.versions.length + 1).padStart(3, '0')}`,
      versionKey: normalized,
      name: normalized,
      isCurrent: false,
      createdAt: new Date().toISOString(),
    };

    this.state.versions.push(version);
    this.state.versionCaseStatus[normalized] = {};
    this.state.cases.forEach((item) => {
      this.state.versionCaseStatus[normalized][item.caseKey] = 'not_run';
    });
    return deepClone(version);
  }

  async setCurrentVersion(versionKey: string): Promise<void> {
    this.getVersion(versionKey);
    this.state.versions.forEach((item) => {
      item.isCurrent = item.versionKey === versionKey;
    });
    this.state.config.currentVersionKey = versionKey;
  }

  async deleteVersion(versionKey: string): Promise<void> {
    if (this.state.config.currentVersionKey === versionKey) {
      throw new MockRepositoryError('VALIDATION_ERROR', '当前版本不可删除');
    }

    const hasIssue = this.state.issues.some((item) =>
      [item.foundVersionKey, item.fixVersionKey, item.verifyVersionKey].includes(versionKey),
    );
    const hasHistory = this.state.caseHistory.some((item) => item.versionKey === versionKey);
    if (hasIssue || hasHistory) {
      throw new MockRepositoryError('VALIDATION_ERROR', '版本下存在执行或问题单数据，禁止删除');
    }

    this.state.versions = this.state.versions.filter((item) => item.versionKey !== versionKey);
    delete this.state.versionCaseStatus[versionKey];
  }

  async listUsers(): Promise<User[]> {
    return deepClone(this.state.users);
  }

  async createUser(payload: Pick<User, 'username' | 'email' | 'role'>): Promise<User> {
    if (this.state.users.some((item) => item.username === payload.username)) {
      throw new MockRepositoryError('VALIDATION_ERROR', '用户名已存在');
    }

    const user: User = {
      userId: `U-${String(this.state.users.length + 1).padStart(3, '0')}`,
      username: payload.username,
      email: payload.email,
      role: payload.role,
      status: 'active',
    };

    this.state.users.push(user);
    return deepClone(user);
  }

  async deleteUser(userId: string): Promise<void> {
    const user = this.findUserById(userId);
    user.status = 'disabled';
  }

  async listCases(versionKey: string): Promise<ModuleCaseGroup[]> {
    this.getVersion(versionKey);
    const cases = this.buildCaseWithStatus(versionKey);
    return deepClone(toModuleGroups(cases));
  }

  async getCaseDetail(versionKey: string, caseKey: string): Promise<CaseDetail> {
    this.getVersion(versionKey);
    const cases = this.buildCaseWithStatus(versionKey);
    const selected = cases.find((item) => item.caseKey === caseKey);
    if (!selected) {
      throw new MockRepositoryError('NOT_FOUND', '用例不存在');
    }

    const history = this.state.caseHistory
      .filter((item) => item.versionKey === versionKey && item.caseKey === caseKey)
      .sort((a, b) => b.executedAt.localeCompare(a.executedAt))
      .slice(0, 10);

    return {
      caseInfo: deepClone(selected),
      history: deepClone(history),
    };
  }

  async updateCaseStatus(payload: UpdateCaseStatusPayload, operator: User): Promise<void> {
    this.getVersion(payload.versionKey);
    const targetCase = this.state.cases.find((item) => item.caseKey === payload.caseKey);
    if (!targetCase) {
      throw new MockRepositoryError('NOT_FOUND', '用例不存在');
    }

    const versionStatuses = this.state.versionCaseStatus[payload.versionKey] ?? {};
    versionStatuses[payload.caseKey] = payload.status;
    this.state.versionCaseStatus[payload.versionKey] = versionStatuses;

    this.state.caseHistory.unshift({
      id: `H-${String(this.state.caseHistory.length + 1).padStart(3, '0')}`,
      versionKey: payload.versionKey,
      caseKey: payload.caseKey,
      status: payload.status,
      executorId: operator.userId,
      executorName: operator.username,
      executedAt: new Date().toISOString(),
      note: payload.note,
      attachments: payload.attachments ?? [],
    });
  }

  async listIssues(query: IssueQuery): Promise<Issue[]> {
    this.getVersion(query.versionKey);
    const list = this.state.issues
      .filter((item) => item.foundVersionKey === query.versionKey)
      .filter((item) => statusMatchesGroup(item.status, query.statusGroup))
      .filter((item) => (query.assigneeId ? item.assigneeId === query.assigneeId : true))
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));

    return deepClone(list);
  }

  async createIssue(payload: CreateIssuePayload): Promise<Issue> {
    this.getVersion(payload.foundVersionKey);
    const reporter = this.findUserById(payload.reporterId);
    const assignee = payload.assigneeId ? this.findUserById(payload.assigneeId) : undefined;

    if (!payload.links.some((item) => item.linkType === 'repro')) {
      throw new MockRepositoryError('VALIDATION_ERROR', '至少需要一个复现用例');
    }

    const issue: Issue = {
      issueId: `I-${String(this.state.issues.length + 1).padStart(3, '0')}`,
      issueKey: `ISS-${String(this.state.issues.length + 1).padStart(3, '0')}`,
      title: payload.title,
      description: payload.description,
      status: 'new',
      priority: payload.priority,
      severity: payload.severity,
      assigneeId: assignee?.userId,
      assigneeName: assignee?.username,
      reporterId: reporter.userId,
      reporterName: reporter.username,
      foundVersionKey: payload.foundVersionKey,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      links: payload.links,
    };

    this.state.issues.unshift(issue);
    return deepClone(issue);
  }

  async updateIssue(
    issueKey: string,
    patch: Partial<Pick<Issue, 'title' | 'description' | 'priority' | 'assigneeId'>>,
  ): Promise<Issue> {
    const issue = this.getIssue(issueKey);

    if (patch.assigneeId) {
      const assignee = this.findUserById(patch.assigneeId);
      issue.assigneeId = assignee.userId;
      issue.assigneeName = assignee.username;
    }

    if (patch.title) {
      issue.title = patch.title;
    }
    if (patch.description) {
      issue.description = patch.description;
    }
    if (patch.priority) {
      issue.priority = patch.priority;
    }

    issue.updatedAt = new Date().toISOString();
    return deepClone(issue);
  }

  async transitionIssue(issueKey: string, nextStatus: Issue['status']): Promise<Issue> {
    const issue = this.getIssue(issueKey);
    issue.status = nextStatus;
    issue.updatedAt = new Date().toISOString();
    return deepClone(issue);
  }

  async closeIssue(issueKey: string, payload: CloseIssuePayload): Promise<Issue> {
    const issue = this.getIssue(issueKey);

    if (!payload.fixVersionKey || !payload.verifyVersionKey) {
      throw new MockRepositoryError('VALIDATION_ERROR', '修复版本和验证版本为必填');
    }
    if (payload.regressionCaseKeys.length === 0) {
      throw new MockRepositoryError('VALIDATION_ERROR', '关闭前必须至少关联一个回归用例');
    }

    this.getVersion(payload.fixVersionKey);
    this.getVersion(payload.verifyVersionKey);

    const missingPassed = payload.regressionCaseKeys.filter((caseKey) => {
      const status = this.state.versionCaseStatus[payload.verifyVersionKey]?.[caseKey] ?? 'not_run';
      return status !== 'passed';
    });

    if (missingPassed.length > 0) {
      throw new MockRepositoryError(
        'VALIDATION_ERROR',
        `以下回归用例在验证版本未通过: ${missingPassed.join(', ')}`,
      );
    }

    payload.regressionCaseKeys.forEach((caseKey) => {
      const existing = issue.links.find((item) => item.caseKey === caseKey && item.linkType === 'regression');
      if (!existing) {
        issue.links.push({ caseKey, linkType: 'regression' });
      }
    });

    issue.fixVersionKey = payload.fixVersionKey;
    issue.verifyVersionKey = payload.verifyVersionKey;
    issue.status = 'closed';
    issue.updatedAt = new Date().toISOString();
    return deepClone(issue);
  }

  async getDashboard(versionKey: string) {
    const cases = this.buildCaseWithStatus(versionKey);
    return calculateDashboardKpi(cases, this.state.issues, versionKey);
  }

  async listPendingIssues(versionKey: string): Promise<Issue[]> {
    return deepClone(
      this.state.issues
        .filter((item) => item.foundVersionKey === versionKey)
        .filter((item) => getIssueStatusGroup(item.status) === 'pending')
        .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)),
    );
  }

  async downloadTemplate(kind: 'cases' | 'issues', format: 'csv' | 'xlsx'): Promise<Blob> {
    const rows: Record<string, string>[] =
      kind === 'cases'
        ? [
            {
              case_key: 'TC-100',
              title: '示例用例',
              module: '用户登录',
              steps: '步骤描述',
              expected: '期望结果',
              tags: '登录,核心流程',
            },
          ]
        : [
            {
              issue_key: 'ISS-100',
              title: '示例问题单',
              description: '问题描述',
              status: 'new',
              priority: 'high',
              severity: 'major',
              found_version_key: 'v1.0.0',
            },
          ];

    return buildWorkbookBlob(rows, format);
  }

  async validateImport(kind: 'cases' | 'issues', file: File): Promise<ImportValidationResult> {
    const rows = await parseRowsFromFile(file);
    const errors: string[] = [];

    rows.forEach((row, index) => {
      if (kind === 'cases') {
        if (!row.case_key) {
          errors.push(`第 ${index + 2} 行缺少 case_key`);
        }
        if (!row.title) {
          errors.push(`第 ${index + 2} 行缺少 title`);
        }
        if (!row.module) {
          errors.push(`第 ${index + 2} 行缺少 module`);
        }
      } else {
        if (!row.issue_key) {
          errors.push(`第 ${index + 2} 行缺少 issue_key`);
        }
        if (!row.title) {
          errors.push(`第 ${index + 2} 行缺少 title`);
        }
        if (!row.found_version_key) {
          errors.push(`第 ${index + 2} 行缺少 found_version_key`);
        }
      }
    });

    const validRows = Math.max(rows.length - errors.length, 0);

    return {
      kind,
      totalRows: rows.length,
      validRows,
      errors,
      preview: rows.slice(0, 20),
    };
  }

  async exportData(kind: 'cases' | 'issues', format: 'csv' | 'xlsx', versionKey: string): Promise<Blob> {
    let rows: Record<string, string>[];

    if (kind === 'cases') {
      const cases = this.buildCaseWithStatus(versionKey);
      rows = cases.map((item) => ({
        case_key: item.caseKey,
        title: item.title,
        module: item.module,
        status: item.latestStatus,
        latest_updated_at: item.latestUpdatedAt ?? '',
      }));
    } else {
      rows = this.state.issues
        .filter((item) => item.foundVersionKey === versionKey)
        .map((item) => ({
          issue_key: item.issueKey,
          title: item.title,
          status: item.status,
          priority: item.priority,
          assignee: item.assigneeName ?? '',
          reporter: item.reporterName,
          found_version_key: item.foundVersionKey,
          updated_at: item.updatedAt,
        }));
    }

    return buildWorkbookBlob(rows, format);
  }

  async getCicdPipeline(pipelineKey: string): Promise<CicdPipeline> {
    if (this.state.cicdPipeline.pipelineKey !== pipelineKey) {
      throw new MockRepositoryError('NOT_FOUND', `流水线不存在: ${pipelineKey}`);
    }
    return deepClone(this.state.cicdPipeline);
  }

  async listCicdRuns(pipelineKey: string): Promise<CicdRun[]> {
    if (this.state.cicdPipeline.pipelineKey !== pipelineKey) {
      throw new MockRepositoryError('NOT_FOUND', `流水线不存在: ${pipelineKey}`);
    }
    return deepClone(
      this.state.cicdRuns
        .filter((item) => item.pipelineKey === pipelineKey)
        .sort((a, b) => b.startedAt.localeCompare(a.startedAt)),
    );
  }

  async triggerCicdRun(payload: TriggerCicdRunPayload): Promise<CicdRun> {
    if (this.state.cicdPipeline.pipelineKey !== payload.pipelineKey) {
      throw new MockRepositoryError('NOT_FOUND', `流水线不存在: ${payload.pipelineKey}`);
    }

    const now = new Date().toISOString();
    const runId = `RUN-${String(this.state.cicdRuns.length + 1).padStart(4, '0')}`;
    const stages: CicdStage[] = this.state.cicdPipeline.stagesTemplate.map((item, index) => ({
      ...item,
      status: index === 0 ? 'running' : 'pending',
      updatedAt: index === 0 ? now : undefined,
      note: index === 0 ? '占位：等待真实构建机回调' : undefined,
    }));

    const run: CicdRun = {
      runId,
      pipelineKey: payload.pipelineKey,
      pipelineName: this.state.cicdPipeline.pipelineName,
      branch: payload.branch,
      commitId: payload.commitId,
      note: payload.note,
      status: 'running',
      triggeredBy: payload.triggeredBy,
      startedAt: now,
      stages,
      logs: [`[trigger] ${payload.triggeredBy} 触发流水线，分支 ${payload.branch}`],
    };

    this.state.cicdRuns.unshift(run);
    return deepClone(run);
  }

  async updateCicdStage(payload: UpdateCicdStagePayload): Promise<CicdRun> {
    const run = this.getCicdRun(payload.runId);
    const stageIndex = run.stages.findIndex((item) => item.stageKey === payload.stageKey);
    if (stageIndex < 0) {
      throw new MockRepositoryError('NOT_FOUND', `阶段不存在: ${payload.stageKey}`);
    }

    const stage = run.stages[stageIndex];
    const now = new Date().toISOString();
    const nextStatus: CicdStageStatus = payload.status;
    stage.status = nextStatus;
    stage.updatedAt = now;
    stage.note = payload.note;
    run.logs.unshift(`[${stage.stageKey}] ${nextStatus}${payload.note ? ` - ${payload.note}` : ''}`);

    if (nextStatus === 'failed') {
      run.status = 'failed';
      run.finishedAt = now;
      return deepClone(run);
    }

    if (nextStatus === 'success') {
      const nextStage = run.stages[stageIndex + 1];
      if (nextStage && nextStage.status === 'pending') {
        nextStage.status = 'running';
        nextStage.updatedAt = now;
        nextStage.note = '占位：等待手动推进或回调';
      }

      const allDone = run.stages.every((item) => item.status === 'success');
      if (allDone) {
        run.status = 'success';
        run.finishedAt = now;
      } else {
        run.status = 'running';
        run.finishedAt = undefined;
      }
      return deepClone(run);
    }

    run.status = 'running';
    run.finishedAt = undefined;
    return deepClone(run);
  }

  async getAutomationFramework(frameworkKey: string): Promise<AutomationFramework> {
    return deepClone(this.getAutomationFrameworkState(frameworkKey));
  }

  async listAutomationRuns(frameworkKey: string): Promise<AutomationRun[]> {
    this.getAutomationFrameworkState(frameworkKey);
    return deepClone(
      this.state.automationRuns
        .filter((item) => item.frameworkKey === frameworkKey)
        .sort((a, b) => b.startedAt.localeCompare(a.startedAt)),
    );
  }

  async saveAutomationConfiguration(payload: SaveAutomationConfigurationPayload): Promise<AutomationFramework> {
    const framework = this.getAutomationFrameworkState(payload.frameworkKey);
    const target = framework.configurations.find((item) => item.configKey === payload.configKey);
    if (!target) {
      throw new MockRepositoryError('NOT_FOUND', `配置不存在: ${payload.configKey}`);
    }

    const now = new Date().toISOString();
    target.content = payload.content;
    target.updatedAt = now;
    target.updatedBy = payload.updatedBy;
    framework.updatedAt = now;
    return deepClone(framework);
  }

  async saveAutomationTestSuite(payload: SaveAutomationTestSuitePayload): Promise<AutomationFramework> {
    const framework = this.getAutomationFrameworkState(payload.frameworkKey);
    const target = framework.testSuites.find((item) => item.suiteKey === payload.suiteKey);
    if (!target) {
      throw new MockRepositoryError('NOT_FOUND', `测试套不存在: ${payload.suiteKey}`);
    }

    const now = new Date().toISOString();
    target.content = payload.content;
    target.updatedAt = now;
    target.updatedBy = payload.updatedBy;
    framework.updatedAt = now;
    return deepClone(framework);
  }

  async triggerAutomationRun(payload: TriggerAutomationRunPayload): Promise<AutomationRun> {
    const framework = this.getAutomationFrameworkState(payload.frameworkKey);
    const selectedConfig = framework.configurations.find((item) => item.configKey === payload.configurationKey);
    if (!selectedConfig) {
      throw new MockRepositoryError('NOT_FOUND', `配置不存在: ${payload.configurationKey}`);
    }
    const selectedSuite = framework.testSuites.find((item) => item.suiteKey === payload.testSuiteKey);
    if (!selectedSuite) {
      throw new MockRepositoryError('NOT_FOUND', `测试套不存在: ${payload.testSuiteKey}`);
    }
    if (!framework.operationModes.some((item) => item.mode === payload.operationMode)) {
      throw new MockRepositoryError('VALIDATION_ERROR', `不支持的执行模式: ${payload.operationMode}`);
    }

    const now = new Date().toISOString();
    const runId = `AUTO-${String(this.state.automationRuns.length + 1).padStart(4, '0')}`;

    const buildLogs = (mode: AutomationOperationMode): string[] => {
      if (framework.frameworkKey === 'frigateDynamic') {
        switch (mode) {
          case 'deploy_pressure_machine':
            return [
              '[deploy_pressure_machine] 占位：连接 172.22.67.76 并部署 frigate',
              '[deploy_pressure_machine] 占位：部署完成，等待下一步动作',
            ];
          case 'deploy_hyperchain':
            return [
              '[deploy_hyperchain] 占位：上传 hyperchain 二进制到 10.10.33.56 指定目录',
              '[deploy_hyperchain] 占位：同步配置文件完成',
            ];
          case 'deploy_and_test':
            return [
              '[deploy_pressure_machine] 占位：部署压力机组件完成',
              '[deploy_hyperchain] 占位：部署被测 hyperchain 完成',
              '[test_only] 占位：通过 SSH 在压力机上启动 frigate 压测',
            ];
          case 'test_only':
            return ['[test_only] 占位：跳过部署，直接触发压测任务'];
          default:
            return ['[unknown] 占位：未定义执行模式'];
        }
      }

      return [
        '[functional_test] 占位：加载 hypersonic 配置与测试套',
        '[functional_test] 占位：执行功能回归并生成报告',
      ];
    };

    const status: AutomationRunStatus = 'success';
    const run: AutomationRun = {
      runId,
      frameworkKey: framework.frameworkKey,
      entryName: framework.entryName,
      configurationKey: payload.configurationKey,
      testSuiteKey: payload.testSuiteKey,
      operationMode: payload.operationMode,
      status,
      note: payload.note,
      triggeredBy: payload.triggeredBy,
      startedAt: now,
      finishedAt: now,
      logs: buildLogs(payload.operationMode),
    };

    this.state.automationRuns.unshift(run);
    return deepClone(run);
  }
}
