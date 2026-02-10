import Papa from 'papaparse';
import type {
  AutomationFramework,
  AutomationOperationMode,
  AutomationRun,
  AutomationRunStatus,
  CaseDetail,
  CaseWithStatus,
  CicdPipeline,
  CicdRun,
  CicdStage,
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
  TriggerAutomationRunPayload,
  TriggerCicdRunPayload,
  UpdateCaseStatusPayload,
  UpdateCicdStagePayload,
  User,
  Version,
} from '../../domain/types';
import type { Repository } from '../repository';
import { STORAGE_KEYS } from '../../utils/storage';

interface Envelope<T> {
  data: T;
  trace_id: string;
}

interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
  trace_id: string;
}

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE';

function buildQuery(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      search.set(key, value);
    }
  });
  const query = search.toString();
  return query ? `?${query}` : '';
}

function toUser(row: {
  user_id: string;
  username: string;
  email: string;
  role: User['role'];
  status: User['status'];
}): User {
  return {
    userId: row.user_id,
    username: row.username,
    email: row.email,
    role: row.role,
    status: row.status,
  };
}

function toVersion(row: {
  version_key: string;
  name: string;
  is_current: boolean;
  created_at: string;
}): Version {
  return {
    versionId: row.version_key,
    versionKey: row.version_key,
    name: row.name,
    isCurrent: row.is_current,
    createdAt: row.created_at,
  };
}

function toIssue(row: {
  issue_key: string;
  title: string;
  description: string;
  status: Issue['status'];
  priority: Issue['priority'];
  severity: Issue['severity'];
  assignee: string | null;
  reporter: string;
  found_version_key: string;
  fix_version_key?: string | null;
  verify_version_key?: string | null;
  created_at: string;
  updated_at: string;
  links: { case_key: string; link_type: 'repro' | 'regression'; note?: string }[];
}): Issue {
  return {
    issueId: row.issue_key,
    issueKey: row.issue_key,
    title: row.title,
    description: row.description,
    status: row.status,
    priority: row.priority,
    severity: row.severity,
    assigneeId: row.assignee ?? undefined,
    assigneeName: row.assignee ?? undefined,
    reporterId: row.reporter,
    reporterName: row.reporter,
    foundVersionKey: row.found_version_key,
    fixVersionKey: row.fix_version_key ?? undefined,
    verifyVersionKey: row.verify_version_key ?? undefined,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    links: row.links.map((link) => ({
      caseKey: link.case_key,
      linkType: link.link_type,
      note: link.note,
    })),
  };
}

function toCicdStage(row: {
  stage_key: string;
  name: string;
  description: string;
  command: string;
  status: CicdStage['status'];
  updated_at?: string | null;
  note?: string | null;
}): CicdStage {
  return {
    stageKey: row.stage_key,
    name: row.name,
    description: row.description,
    command: row.command,
    status: row.status,
    updatedAt: row.updated_at ?? undefined,
    note: row.note ?? undefined,
  };
}

function toAutomationFramework(row: {
  framework_key: string;
  entry_name: string;
  display_name: string;
  framework_type: 'performance' | 'functional';
  description: string;
  streamlit_url?: string | null;
  build_machine: { name: string; ip: string; note: string };
  deploy_target: { name: string; ip: string; note: string };
  configurations: {
    config_key: string;
    name: string;
    description: string;
    content: string;
    updated_at: string;
    updated_by: string;
  }[];
  test_suites: {
    suite_key: string;
    name: string;
    description: string;
    content: string;
    updated_at: string;
    updated_by: string;
  }[];
  operation_modes: {
    mode: AutomationOperationMode;
    label: string;
    description: string;
  }[];
  updated_at: string;
}): AutomationFramework {
  return {
    frameworkKey: row.framework_key as AutomationFramework['frameworkKey'],
    entryName: row.entry_name,
    displayName: row.display_name,
    frameworkType: row.framework_type,
    description: row.description,
    streamlitUrl: row.streamlit_url ?? undefined,
    buildMachine: row.build_machine,
    deployTarget: row.deploy_target,
    configurations: row.configurations.map((item) => ({
      configKey: item.config_key,
      name: item.name,
      description: item.description,
      content: item.content,
      updatedAt: item.updated_at,
      updatedBy: item.updated_by,
    })),
    testSuites: row.test_suites.map((item) => ({
      suiteKey: item.suite_key,
      name: item.name,
      description: item.description,
      content: item.content,
      updatedAt: item.updated_at,
      updatedBy: item.updated_by,
    })),
    operationModes: row.operation_modes,
    updatedAt: row.updated_at,
  };
}

function toAutomationRun(row: {
  run_id: string;
  framework_key: string;
  entry_name: string;
  configuration_key: string;
  test_suite_key: string;
  operation_mode: AutomationOperationMode;
  status: AutomationRunStatus;
  note?: string | null;
  triggered_by: string;
  started_at: string;
  finished_at?: string | null;
  logs: string[];
}): AutomationRun {
  return {
    runId: row.run_id,
    frameworkKey: row.framework_key as AutomationRun['frameworkKey'],
    entryName: row.entry_name,
    configurationKey: row.configuration_key,
    testSuiteKey: row.test_suite_key,
    operationMode: row.operation_mode,
    status: row.status,
    note: row.note ?? undefined,
    triggeredBy: row.triggered_by,
    startedAt: row.started_at,
    finishedAt: row.finished_at ?? undefined,
    logs: row.logs,
  };
}

export class HttpRepository implements Repository {
  private readonly baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    method: HttpMethod,
    path: string,
    options?: {
      jsonBody?: unknown;
      formData?: FormData;
      expectBlob?: boolean;
      tokenOverride?: string;
    },
  ): Promise<T> {
    const headers: Record<string, string> = {};
    const token = options?.tokenOverride ?? localStorage.getItem(STORAGE_KEYS.token);
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    let body: BodyInit | undefined;
    if (options?.jsonBody !== undefined) {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(options.jsonBody);
    }
    if (options?.formData) {
      body = options.formData;
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers,
      body,
    });

    if (options?.expectBlob) {
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || '请求失败');
      }
      return (await response.blob()) as T;
    }

    const payload = (await response.json()) as Envelope<T> | ErrorEnvelope;
    if (!response.ok) {
      if ('error' in payload) {
        throw new Error(payload.error.message);
      }
      throw new Error('请求失败');
    }

    return (payload as Envelope<T>).data;
  }

  async login(payload: LoginPayload): Promise<LoginResult> {
    const data = await this.request<{
      access_token: string;
      token_type: string;
      user: {
        user_id: string;
        username: string;
        email: string;
        role: User['role'];
        status: User['status'];
      };
    }>('POST', '/auth/login', { jsonBody: payload });

    return {
      accessToken: data.access_token,
      user: toUser(data.user),
    };
  }

  async getCurrentUser(token: string): Promise<User> {
    const data = await this.request<{
      user_id: string;
      username: string;
      email: string;
      role: User['role'];
      status: User['status'];
    }>('GET', '/auth/me', { tokenOverride: token });
    return toUser(data);
  }

  async getConfig(): Promise<ProjectConfig> {
    const data = await this.request<{ project_name: string; current_version_key: string }>('GET', '/config');
    return {
      projectName: data.project_name,
      currentVersionKey: data.current_version_key,
    };
  }

  async updateConfig(projectName: string): Promise<ProjectConfig> {
    const data = await this.request<{ project_name: string; current_version_key: string }>('PUT', '/config', {
      jsonBody: { project_name: projectName },
    });
    return {
      projectName: data.project_name,
      currentVersionKey: data.current_version_key,
    };
  }

  async listVersions(): Promise<Version[]> {
    const data = await this.request<
      {
        version_key: string;
        name: string;
        is_current: boolean;
        created_at: string;
      }[]
    >('GET', '/versions');
    return data.map(toVersion);
  }

  async createVersion(versionKey: string): Promise<Version> {
    const data = await this.request<{
      version_key: string;
      name: string;
      is_current: boolean;
      created_at: string;
    }>('POST', '/versions', { jsonBody: { version_key: versionKey } });
    return toVersion(data);
  }

  async setCurrentVersion(versionKey: string): Promise<void> {
    await this.request('POST', `/versions/${encodeURIComponent(versionKey)}:set-current`);
  }

  async deleteVersion(versionKey: string): Promise<void> {
    await this.request('DELETE', `/versions/${encodeURIComponent(versionKey)}`);
  }

  async listUsers(): Promise<User[]> {
    const data = await this.request<
      {
        user_id: string;
        username: string;
        email: string;
        role: User['role'];
        status: User['status'];
      }[]
    >('GET', '/users');
    return data.map(toUser);
  }

  async createUser(payload: Pick<User, 'username' | 'email' | 'role'>): Promise<User> {
    const data = await this.request<{
      user_id: string;
      username: string;
      email: string;
      role: User['role'];
      status: User['status'];
    }>('POST', '/users', {
      jsonBody: {
        username: payload.username,
        email: payload.email,
        role: payload.role,
      },
    });
    return toUser(data);
  }

  async deleteUser(userId: string): Promise<void> {
    await this.request('DELETE', `/users/${encodeURIComponent(userId)}`);
  }

  async listCases(versionKey: string): Promise<ModuleCaseGroup[]> {
    const data = await this.request<
      {
        module: string;
        cases: {
          case_key: string;
          title: string;
          module: string;
          latest_status: CaseWithStatus['latestStatus'];
          latest_updated_at: string | null;
          latest_updated_by: string | null;
        }[];
      }[]
    >('GET', `/cases${buildQuery({ version_key: versionKey, group_by: 'module' })}`);

    return data.map((group) => ({
      module: group.module,
      cases: group.cases.map((item) => ({
        caseId: item.case_key,
        caseKey: item.case_key,
        title: item.title,
        steps: '',
        expected: '',
        module: item.module,
        tags: [],
        status: 'active',
        latestStatus: item.latest_status,
        latestUpdatedAt: item.latest_updated_at ?? undefined,
        latestUpdatedBy: item.latest_updated_by ?? undefined,
      })),
    }));
  }

  async getCaseDetail(versionKey: string, caseKey: string): Promise<CaseDetail> {
    const data = await this.request<{
      case_info: {
        case_key: string;
        title: string;
        module: string;
        steps: string;
        expected: string;
        tags: string[];
        latest_status: CaseWithStatus['latestStatus'];
      };
      history: {
        id: number;
        executed_at: string;
        executor: string;
        status: CaseWithStatus['latestStatus'];
        note: string | null;
        attachments: { name: string; url: string; size?: number; mime?: string }[];
      }[];
    }>('GET', `/cases/${encodeURIComponent(caseKey)}${buildQuery({ version_key: versionKey })}`);

    return {
      caseInfo: {
        caseId: data.case_info.case_key,
        caseKey: data.case_info.case_key,
        title: data.case_info.title,
        steps: data.case_info.steps,
        expected: data.case_info.expected,
        module: data.case_info.module,
        tags: data.case_info.tags,
        status: 'active',
        latestStatus: data.case_info.latest_status,
      },
      history: data.history.map((item) => ({
        id: String(item.id),
        versionKey,
        caseKey,
        status: item.status,
        executorId: item.executor,
        executorName: item.executor,
        executedAt: item.executed_at,
        note: item.note ?? undefined,
        attachments: item.attachments ?? [],
      })),
    };
  }

  async updateCaseStatus(payload: UpdateCaseStatusPayload, operator: User): Promise<void> {
    await this.request('PUT', `/versions/${encodeURIComponent(payload.versionKey)}/cases/${encodeURIComponent(payload.caseKey)}/status`, {
      jsonBody: {
        status: payload.status,
        note: payload.note,
        attachments: payload.attachments ?? [],
        operator: operator.userId,
      },
    });
  }

  async listIssues(query: IssueQuery): Promise<Issue[]> {
    const data = await this.request<
      {
        issue_key: string;
        title: string;
        description: string;
        status: Issue['status'];
        priority: Issue['priority'];
        severity: Issue['severity'];
        assignee: string | null;
        reporter: string;
        found_version_key: string;
        fix_version_key?: string | null;
        verify_version_key?: string | null;
        created_at: string;
        updated_at: string;
        links: { case_key: string; link_type: 'repro' | 'regression'; note?: string }[];
      }[]
    >(
      'GET',
      `/issues${buildQuery({
        version_key: query.versionKey,
        status_group: query.statusGroup,
        assignee: query.assigneeId,
      })}`,
    );

    return data.map(toIssue);
  }

  async createIssue(payload: CreateIssuePayload): Promise<Issue> {
    const data = await this.request<{
      issue_key: string;
      title: string;
      description: string;
      status: Issue['status'];
      priority: Issue['priority'];
      severity: Issue['severity'];
      assignee: string | null;
      reporter: string;
      found_version_key: string;
      fix_version_key?: string | null;
      verify_version_key?: string | null;
      created_at: string;
      updated_at: string;
      links: { case_key: string; link_type: 'repro' | 'regression'; note?: string }[];
    }>('POST', '/issues', {
      jsonBody: {
        title: payload.title,
        description: payload.description,
        priority: payload.priority,
        severity: payload.severity,
        assignee: payload.assigneeId,
        reporter: payload.reporterId,
        found_version_key: payload.foundVersionKey,
        links: payload.links.map((link) => ({
          case_key: link.caseKey,
          link_type: link.linkType,
          note: link.note,
        })),
      },
    });

    return toIssue(data);
  }

  async updateIssue(
    issueKey: string,
    patch: Partial<Pick<Issue, 'title' | 'description' | 'priority' | 'assigneeId'>>,
  ): Promise<Issue> {
    const data = await this.request<{
      issue_key: string;
      title: string;
      description: string;
      status: Issue['status'];
      priority: Issue['priority'];
      severity: Issue['severity'];
      assignee: string | null;
      reporter: string;
      found_version_key: string;
      fix_version_key?: string | null;
      verify_version_key?: string | null;
      created_at: string;
      updated_at: string;
      links: { case_key: string; link_type: 'repro' | 'regression'; note?: string }[];
    }>('PUT', `/issues/${encodeURIComponent(issueKey)}`, {
      jsonBody: {
        title: patch.title,
        description: patch.description,
        priority: patch.priority,
        assignee: patch.assigneeId,
      },
    });

    return toIssue(data);
  }

  async transitionIssue(issueKey: string, nextStatus: Issue['status']): Promise<Issue> {
    const data = await this.request<{
      issue_key: string;
      title: string;
      description: string;
      status: Issue['status'];
      priority: Issue['priority'];
      severity: Issue['severity'];
      assignee: string | null;
      reporter: string;
      found_version_key: string;
      fix_version_key?: string | null;
      verify_version_key?: string | null;
      created_at: string;
      updated_at: string;
      links: { case_key: string; link_type: 'repro' | 'regression'; note?: string }[];
    }>('POST', `/issues/${encodeURIComponent(issueKey)}:transition`, {
      jsonBody: { target_status: nextStatus },
    });

    return toIssue(data);
  }

  async closeIssue(issueKey: string, payload: CloseIssuePayload): Promise<Issue> {
    const data = await this.request<{
      issue_key: string;
      title: string;
      description: string;
      status: Issue['status'];
      priority: Issue['priority'];
      severity: Issue['severity'];
      assignee: string | null;
      reporter: string;
      found_version_key: string;
      fix_version_key?: string | null;
      verify_version_key?: string | null;
      created_at: string;
      updated_at: string;
      links: { case_key: string; link_type: 'repro' | 'regression'; note?: string }[];
    }>('POST', `/issues/${encodeURIComponent(issueKey)}:close`, {
      jsonBody: {
        fix_version_key: payload.fixVersionKey,
        verify_version_key: payload.verifyVersionKey,
        regression_case_keys: payload.regressionCaseKeys,
      },
    });
    return toIssue(data);
  }

  async getDashboard(versionKey: string): Promise<DashboardKpi> {
    const data = await this.request<DashboardKpi>('GET', `/dashboard/quality${buildQuery({ version_key: versionKey })}`);
    return data;
  }

  async listPendingIssues(versionKey: string): Promise<Issue[]> {
    const data = await this.request<
      {
        issue_key: string;
        title: string;
        description: string;
        status: Issue['status'];
        priority: Issue['priority'];
        severity: Issue['severity'];
        assignee: string | null;
        reporter: string;
        found_version_key: string;
        fix_version_key?: string | null;
        verify_version_key?: string | null;
        created_at: string;
        updated_at: string;
        links: { case_key: string; link_type: 'repro' | 'regression'; note?: string }[];
      }[]
    >('GET', `/dashboard/issues/pending${buildQuery({ version_key: versionKey })}`);
    return data.map(toIssue);
  }

  async downloadTemplate(kind: 'cases' | 'issues', format: 'csv' | 'xlsx'): Promise<Blob> {
    const headers =
      kind === 'cases'
        ? ['case_key', 'title', 'module', 'steps', 'expected', 'tags']
        : ['issue_key', 'title', 'description', 'status', 'priority', 'severity', 'found_version_key'];

    if (format === 'xlsx') {
      const csv = Papa.unparse([headers]);
      return new Blob([csv], { type: 'text/csv;charset=utf-8' });
    }

    const csv = `${headers.join(',')}\n`;
    return new Blob([csv], { type: 'text/csv;charset=utf-8' });
  }

  async validateImport(kind: 'cases' | 'issues', file: File): Promise<ImportValidationResult> {
    const formData = new FormData();
    formData.append('file', file);

    const path = kind === 'cases' ? '/cases:import' : '/issues:import';
    const data = await this.request<{ total_rows: number; valid_rows: number; errors: string[] }>(
      'POST',
      `${path}${buildQuery({ validate_only: 'true' })}`,
      { formData },
    );

    return {
      kind,
      totalRows: data.total_rows,
      validRows: data.valid_rows,
      errors: data.errors,
      preview: [],
    };
  }

  async exportData(kind: 'cases' | 'issues', format: 'csv' | 'xlsx', versionKey: string): Promise<Blob> {
    const path = kind === 'cases' ? '/cases:export' : '/issues:export';
    return this.request<Blob>('GET', `${path}${buildQuery({ version_key: versionKey, format })}`, {
      expectBlob: true,
    });
  }

  async getCicdPipeline(pipelineKey: string): Promise<CicdPipeline> {
    const data = await this.request<{
      pipeline_key: string;
      pipeline_name: string;
      project_name: string;
      binary_name: string;
      build_machine: { name: string; ip: string; note: string };
      deploy_target: { name: string; ip: string; note: string };
      build_script_path: string;
      artifact_path: string;
      deploy_path: string;
      stages_template: {
        stage_key: string;
        name: string;
        description: string;
        command: string;
      }[];
      updated_at: string;
    }>('GET', `/cicd/pipelines/${encodeURIComponent(pipelineKey)}`);

    return {
      pipelineKey: data.pipeline_key,
      pipelineName: data.pipeline_name,
      projectName: data.project_name,
      binaryName: data.binary_name,
      buildMachine: data.build_machine,
      deployTarget: data.deploy_target,
      buildScriptPath: data.build_script_path,
      artifactPath: data.artifact_path,
      deployPath: data.deploy_path,
      stagesTemplate: data.stages_template.map((item) => ({
        stageKey: item.stage_key,
        name: item.name,
        description: item.description,
        command: item.command,
      })),
      updatedAt: data.updated_at,
    };
  }

  async listCicdRuns(pipelineKey: string): Promise<CicdRun[]> {
    const data = await this.request<
      {
        run_id: string;
        pipeline_key: string;
        pipeline_name: string;
        branch: string;
        commit_id?: string | null;
        note?: string | null;
        status: CicdRun['status'];
        triggered_by: string;
        started_at: string;
        finished_at?: string | null;
        stages: {
          stage_key: string;
          name: string;
          description: string;
          command: string;
          status: CicdStage['status'];
          updated_at?: string | null;
          note?: string | null;
        }[];
        logs: string[];
      }[]
    >('GET', `/cicd/pipelines/${encodeURIComponent(pipelineKey)}/runs`);

    return data.map((item) => ({
      runId: item.run_id,
      pipelineKey: item.pipeline_key,
      pipelineName: item.pipeline_name,
      branch: item.branch,
      commitId: item.commit_id ?? undefined,
      note: item.note ?? undefined,
      status: item.status,
      triggeredBy: item.triggered_by,
      startedAt: item.started_at,
      finishedAt: item.finished_at ?? undefined,
      stages: item.stages.map(toCicdStage),
      logs: item.logs,
    }));
  }

  async triggerCicdRun(payload: TriggerCicdRunPayload): Promise<CicdRun> {
    const data = await this.request<{
      run_id: string;
      pipeline_key: string;
      pipeline_name: string;
      branch: string;
      commit_id?: string | null;
      note?: string | null;
      status: CicdRun['status'];
      triggered_by: string;
      started_at: string;
      finished_at?: string | null;
      stages: {
        stage_key: string;
        name: string;
        description: string;
        command: string;
        status: CicdStage['status'];
        updated_at?: string | null;
        note?: string | null;
      }[];
      logs: string[];
    }>('POST', `/cicd/pipelines/${encodeURIComponent(payload.pipelineKey)}/runs`, {
      jsonBody: {
        branch: payload.branch,
        commit_id: payload.commitId,
        note: payload.note,
        triggered_by: payload.triggeredBy,
      },
    });

    return {
      runId: data.run_id,
      pipelineKey: data.pipeline_key,
      pipelineName: data.pipeline_name,
      branch: data.branch,
      commitId: data.commit_id ?? undefined,
      note: data.note ?? undefined,
      status: data.status,
      triggeredBy: data.triggered_by,
      startedAt: data.started_at,
      finishedAt: data.finished_at ?? undefined,
      stages: data.stages.map(toCicdStage),
      logs: data.logs,
    };
  }

  async updateCicdStage(payload: UpdateCicdStagePayload): Promise<CicdRun> {
    const data = await this.request<{
      run_id: string;
      pipeline_key: string;
      pipeline_name: string;
      branch: string;
      commit_id?: string | null;
      note?: string | null;
      status: CicdRun['status'];
      triggered_by: string;
      started_at: string;
      finished_at?: string | null;
      stages: {
        stage_key: string;
        name: string;
        description: string;
        command: string;
        status: CicdStage['status'];
        updated_at?: string | null;
        note?: string | null;
      }[];
      logs: string[];
    }>('POST', `/cicd/runs/${encodeURIComponent(payload.runId)}/stages/${encodeURIComponent(payload.stageKey)}:update`, {
      jsonBody: {
        status: payload.status,
        note: payload.note,
      },
    });

    return {
      runId: data.run_id,
      pipelineKey: data.pipeline_key,
      pipelineName: data.pipeline_name,
      branch: data.branch,
      commitId: data.commit_id ?? undefined,
      note: data.note ?? undefined,
      status: data.status,
      triggeredBy: data.triggered_by,
      startedAt: data.started_at,
      finishedAt: data.finished_at ?? undefined,
      stages: data.stages.map(toCicdStage),
      logs: data.logs,
    };
  }

  async getAutomationFramework(frameworkKey: string): Promise<AutomationFramework> {
    const data = await this.request<{
      framework_key: string;
      entry_name: string;
      display_name: string;
      framework_type: 'performance' | 'functional';
      description: string;
      streamlit_url?: string | null;
      build_machine: { name: string; ip: string; note: string };
      deploy_target: { name: string; ip: string; note: string };
      configurations: {
        config_key: string;
        name: string;
        description: string;
        content: string;
        updated_at: string;
        updated_by: string;
      }[];
      test_suites: {
        suite_key: string;
        name: string;
        description: string;
        content: string;
        updated_at: string;
        updated_by: string;
      }[];
      operation_modes: {
        mode: AutomationOperationMode;
        label: string;
        description: string;
      }[];
      updated_at: string;
    }>('GET', `/automation/frameworks/${encodeURIComponent(frameworkKey)}`);

    return toAutomationFramework(data);
  }

  async listAutomationRuns(frameworkKey: string): Promise<AutomationRun[]> {
    const data = await this.request<
      {
        run_id: string;
        framework_key: string;
        entry_name: string;
        configuration_key: string;
        test_suite_key: string;
        operation_mode: AutomationOperationMode;
        status: AutomationRunStatus;
        note?: string | null;
        triggered_by: string;
        started_at: string;
        finished_at?: string | null;
        logs: string[];
      }[]
    >('GET', `/automation/frameworks/${encodeURIComponent(frameworkKey)}/runs`);

    return data.map(toAutomationRun);
  }

  async saveAutomationConfiguration(payload: SaveAutomationConfigurationPayload): Promise<AutomationFramework> {
    const data = await this.request<{
      framework_key: string;
      entry_name: string;
      display_name: string;
      framework_type: 'performance' | 'functional';
      description: string;
      streamlit_url?: string | null;
      build_machine: { name: string; ip: string; note: string };
      deploy_target: { name: string; ip: string; note: string };
      configurations: {
        config_key: string;
        name: string;
        description: string;
        content: string;
        updated_at: string;
        updated_by: string;
      }[];
      test_suites: {
        suite_key: string;
        name: string;
        description: string;
        content: string;
        updated_at: string;
        updated_by: string;
      }[];
      operation_modes: {
        mode: AutomationOperationMode;
        label: string;
        description: string;
      }[];
      updated_at: string;
    }>(
      'PUT',
      `/automation/frameworks/${encodeURIComponent(payload.frameworkKey)}/configurations/${encodeURIComponent(payload.configKey)}`,
      {
        jsonBody: {
          content: payload.content,
          updated_by: payload.updatedBy,
        },
      },
    );

    return toAutomationFramework(data);
  }

  async saveAutomationTestSuite(payload: SaveAutomationTestSuitePayload): Promise<AutomationFramework> {
    const data = await this.request<{
      framework_key: string;
      entry_name: string;
      display_name: string;
      framework_type: 'performance' | 'functional';
      description: string;
      streamlit_url?: string | null;
      build_machine: { name: string; ip: string; note: string };
      deploy_target: { name: string; ip: string; note: string };
      configurations: {
        config_key: string;
        name: string;
        description: string;
        content: string;
        updated_at: string;
        updated_by: string;
      }[];
      test_suites: {
        suite_key: string;
        name: string;
        description: string;
        content: string;
        updated_at: string;
        updated_by: string;
      }[];
      operation_modes: {
        mode: AutomationOperationMode;
        label: string;
        description: string;
      }[];
      updated_at: string;
    }>(
      'PUT',
      `/automation/frameworks/${encodeURIComponent(payload.frameworkKey)}/testsuites/${encodeURIComponent(payload.suiteKey)}`,
      {
        jsonBody: {
          content: payload.content,
          updated_by: payload.updatedBy,
        },
      },
    );

    return toAutomationFramework(data);
  }

  async triggerAutomationRun(payload: TriggerAutomationRunPayload): Promise<AutomationRun> {
    const data = await this.request<{
      run_id: string;
      framework_key: string;
      entry_name: string;
      configuration_key: string;
      test_suite_key: string;
      operation_mode: AutomationOperationMode;
      status: AutomationRunStatus;
      note?: string | null;
      triggered_by: string;
      started_at: string;
      finished_at?: string | null;
      logs: string[];
    }>('POST', `/automation/frameworks/${encodeURIComponent(payload.frameworkKey)}/runs`, {
      jsonBody: {
        configuration_key: payload.configurationKey,
        test_suite_key: payload.testSuiteKey,
        operation_mode: payload.operationMode,
        note: payload.note,
        triggered_by: payload.triggeredBy,
      },
    });

    return toAutomationRun(data);
  }
}
