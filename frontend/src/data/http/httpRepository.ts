import Papa from 'papaparse';
import type {
  AutomationFramework,
  AutomationOperationMode,
  AutomationRun,
  AutomationRunLogChunk,
  AutomationRunStatus,
  CaseTreeNode,
  CaseTreeNodeType,
  CaseDetail,
  CaseWithStatus,
  CicdRunLogChunk,
  CicdPipeline,
  CicdRun,
  CicdStage,
  CloseIssuePayload,
  CreatePlanPayload,
  CreateRunPayload,
  CreateSuitePayload,
  UpdateSuitePayload,
  CreateIssuePayload,
  CreateCasePayload,
  UpdateCasePayload,
  CreateCaseTreeNodePayload,
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
  SuiteCaseSummary,
  SuiteVersion,
  SuiteVersionDetail,
  TriggerAutomationRunPayload,
  TriggerCicdRunPayload,
  UpdateCaseStatusPayload,
  UpdateRunCaseStatusPayload,
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

type RequestError = Error & {
  code?: string;
  details?: Record<string, unknown>;
  status?: number;
};

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

interface CaseTreeNodeRow {
  node_id: string;
  name: string;
  node_type: CaseTreeNodeType;
  parent_node_id?: string | null;
  full_path: string;
  children: CaseTreeNodeRow[];
  cases: {
    case_key: string;
    title: string;
    module: string;
    latest_status: CaseWithStatus['latestStatus'];
  }[];
}

function toCaseTreeNode(row: CaseTreeNodeRow): CaseTreeNode {
  return {
    nodeId: row.node_id,
    name: row.name,
    nodeType: row.node_type,
    parentNodeId: row.parent_node_id ?? undefined,
    fullPath: row.full_path,
    children: row.children.map((item) => toCaseTreeNode(item)),
    cases: row.cases.map((item) => ({
      caseKey: item.case_key,
      title: item.title,
      module: item.module,
      latestStatus: item.latest_status,
    })),
  };
}

function toSuiteVersion(row: {
  suite_version_key: string;
  suite_key: string;
  ver_no: number;
  status: SuiteVersion['status'];
  note?: string | null;
  case_count: number;
  created_at: string;
  published_at?: string | null;
}): SuiteVersion {
  return {
    suiteVersionKey: row.suite_version_key,
    suiteKey: row.suite_key,
    verNo: row.ver_no,
    status: row.status,
    note: row.note ?? undefined,
    caseCount: row.case_count,
    createdAt: row.created_at,
    publishedAt: row.published_at ?? undefined,
  };
}

function toSuite(row: {
  suite_key: string;
  version_key: string;
  name: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
  versions: {
    suite_version_key: string;
    suite_key: string;
    ver_no: number;
    status: SuiteVersion['status'];
    note?: string | null;
    case_count: number;
    created_at: string;
    published_at?: string | null;
  }[];
}): Suite {
  return {
    suiteKey: row.suite_key,
    versionKey: row.version_key,
    name: row.name,
    description: row.description ?? undefined,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    versions: (row.versions ?? []).map((item) => toSuiteVersion(item)),
  };
}

function toPlan(row: {
  plan_key: string;
  version_key: string;
  suite_version_key: string;
  name: string;
  description?: string | null;
  status: Plan['status'];
  created_at: string;
  updated_at: string;
  run_count: number;
  pass_rate?: number | null;
}): Plan {
  return {
    planKey: row.plan_key,
    versionKey: row.version_key,
    suiteVersionKey: row.suite_version_key,
    name: row.name,
    description: row.description ?? undefined,
    status: row.status,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    runCount: row.run_count,
    passRate: row.pass_rate ?? undefined,
  };
}

function toRun(row: {
  run_key: string;
  plan_key: string;
  version_key: string;
  name: string;
  build_no?: string | null;
  environment?: string | null;
  status: Run['status'];
  created_at: string;
  started_at: string;
  finished_at?: string | null;
  pass_rate?: number | null;
  executed_cases: number;
  total_cases: number;
}): Run {
  return {
    runKey: row.run_key,
    planKey: row.plan_key,
    versionKey: row.version_key,
    name: row.name,
    buildNo: row.build_no ?? undefined,
    environment: row.environment ?? undefined,
    status: row.status,
    createdAt: row.created_at,
    startedAt: row.started_at,
    finishedAt: row.finished_at ?? undefined,
    passRate: row.pass_rate ?? undefined,
    executedCases: row.executed_cases,
    totalCases: row.total_cases,
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
  logs?: string[];
  report_archive_path?: string | null;
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
    logs: row.logs ?? [],
    reportArchivePath: row.report_archive_path ?? undefined,
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
        const error = new Error(errorText || '请求失败') as RequestError;
        error.status = response.status;
        throw error;
      }
      return (await response.blob()) as T;
    }

    const rawText = await response.text();
    let payload: Envelope<T> | ErrorEnvelope | null = null;
    if (rawText) {
      try {
        payload = JSON.parse(rawText) as Envelope<T> | ErrorEnvelope;
      } catch {
        payload = null;
      }
    }
    if (!response.ok) {
      if (payload && 'error' in payload) {
        const error = new Error(payload.error.message) as RequestError;
        error.code = payload.error.code;
        error.details = payload.error.details;
        error.status = response.status;
        throw error;
      }
      const error = new Error(rawText || '请求失败') as RequestError;
      error.status = response.status;
      throw error;
    }

    if (!payload || !('data' in payload)) {
      throw new Error('响应数据格式不正确');
    }
    return payload.data;
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

  async listCaseTree(versionKey: string): Promise<CaseTreeNode[]> {
    const data = await this.request<{
      version_key: string;
      tree: CaseTreeNodeRow[];
    }>('GET', `/case-tree${buildQuery({ version_key: versionKey })}`);
    return data.tree.map((item) => toCaseTreeNode(item));
  }

  async createCaseTreeNode(payload: CreateCaseTreeNodePayload): Promise<CaseTreeNode> {
    const data = await this.request<CaseTreeNodeRow>('POST', '/case-tree/nodes', {
      jsonBody: {
        version_key: payload.versionKey,
        parent_node_id: payload.parentNodeId ?? null,
        name: payload.name,
        node_type: payload.nodeType,
      },
    });
    return toCaseTreeNode({ ...data, children: data.children ?? [], cases: data.cases ?? [] });
  }

  async createCase(payload: CreateCasePayload): Promise<void> {
    await this.request('POST', '/cases', {
      jsonBody: {
        version_key: payload.versionKey,
        parent_node_id: payload.parentNodeId,
        case_key: payload.caseKey,
        title: payload.title,
        steps: payload.steps,
        expected: payload.expected,
        tags: payload.tags,
      },
    });
  }

  async updateCase(payload: UpdateCasePayload): Promise<void> {
    await this.request('PUT', `/cases/${encodeURIComponent(payload.caseKey)}`, {
      jsonBody: {
        parent_node_id: payload.parentNodeId ?? null,
        title: payload.title,
        steps: payload.steps,
        expected: payload.expected,
        tags: payload.tags,
      },
    });
  }

  async deleteCase(caseKey: string): Promise<void> {
    await this.request('DELETE', `/cases/${encodeURIComponent(caseKey)}`);
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

  async listSuites(versionKey: string): Promise<Suite[]> {
    const data = await this.request<
      {
        suite_key: string;
        version_key: string;
        name: string;
        description?: string | null;
        created_at: string;
        updated_at: string;
        versions: {
          suite_version_key: string;
          suite_key: string;
          ver_no: number;
          status: SuiteVersion['status'];
          note?: string | null;
          case_count: number;
          created_at: string;
          published_at?: string | null;
        }[];
      }[]
    >('GET', `/suites${buildQuery({ version_key: versionKey })}`);
    return data.map((item) => toSuite(item));
  }

  async createSuite(payload: CreateSuitePayload): Promise<Suite> {
    const data = await this.request<{
      suite_key: string;
      version_key: string;
      name: string;
      description?: string | null;
      created_at: string;
      updated_at: string;
      versions: {
        suite_version_key: string;
        suite_key: string;
        ver_no: number;
        status: SuiteVersion['status'];
        note?: string | null;
        case_count: number;
        created_at: string;
        published_at?: string | null;
      }[];
    }>('POST', '/suites', {
      jsonBody: {
        version_key: payload.versionKey,
        name: payload.name,
        description: payload.description,
        case_keys: payload.caseKeys,
      },
    });
    return toSuite(data);
  }

  async updateSuite(payload: UpdateSuitePayload): Promise<Suite> {
    const data = await this.request<{
      suite_key: string;
      version_key: string;
      name: string;
      description?: string | null;
      created_at: string;
      updated_at: string;
      versions: {
        suite_version_key: string;
        suite_key: string;
        ver_no: number;
        status: SuiteVersion['status'];
        note?: string | null;
        case_count: number;
        created_at: string;
        published_at?: string | null;
      }[];
    }>('PUT', `/suites/${encodeURIComponent(payload.suiteKey)}`, {
      jsonBody: {
        name: payload.name,
        description: payload.description,
      },
    });
    return toSuite(data);
  }

  async deleteSuite(suiteKey: string, suiteVersionKey: string): Promise<void> {
    await this.request('DELETE', `/suites/${encodeURIComponent(suiteKey)}${buildQuery({ suite_version_key: suiteVersionKey })}`);
  }

  async getSuiteVersionDetail(suiteKey: string, suiteVersionKey: string): Promise<SuiteVersionDetail> {
    const data = await this.request<{
      suite_key: string;
      name: string;
      description?: string | null;
      suite_version: {
        suite_version_key: string;
        suite_key?: string;
        ver_no: number;
        status: SuiteVersion['status'];
        note?: string | null;
        case_count: number;
        created_at: string;
        published_at?: string | null;
      };
      cases: {
        case_key: string;
        title: string;
        module: string;
        status: SuiteCaseSummary['status'];
        issue_linked?: boolean;
      }[];
    }>('GET', `/suites/${encodeURIComponent(suiteKey)}/versions/${encodeURIComponent(suiteVersionKey)}`);

    return {
      suiteKey: data.suite_key,
      name: data.name,
      description: data.description ?? undefined,
      suiteVersion: toSuiteVersion({
        ...data.suite_version,
        suite_key: data.suite_key,
      }),
      cases: data.cases.map((item) => ({
        caseKey: item.case_key,
        title: item.title,
        module: item.module,
        status: item.status,
        issueLinked: Boolean(item.issue_linked),
      })),
    };
  }

  async deriveSuiteVersion(suiteKey: string, note?: string): Promise<SuiteVersion> {
    const data = await this.request<{
      suite_version_key: string;
      suite_key: string;
      ver_no: number;
      status: SuiteVersion['status'];
      note?: string | null;
      case_count: number;
      created_at: string;
      published_at?: string | null;
    }>('POST', `/suites/${encodeURIComponent(suiteKey)}/versions`, { jsonBody: { note } });
    return toSuiteVersion(data);
  }

  async publishSuiteVersion(suiteKey: string, suiteVersionKey: string): Promise<SuiteVersion> {
    const data = await this.request<{
      suite_version_key: string;
      suite_key: string;
      ver_no: number;
      status: SuiteVersion['status'];
      note?: string | null;
      case_count: number;
      created_at: string;
      published_at?: string | null;
    }>('POST', `/suites/${encodeURIComponent(suiteKey)}/versions/${encodeURIComponent(suiteVersionKey)}/publish`);
    return toSuiteVersion(data);
  }

  async addSuiteCases(suiteKey: string, suiteVersionKey: string, caseKeys: string[]): Promise<void> {
    await this.request('POST', `/suites/${encodeURIComponent(suiteKey)}/versions/${encodeURIComponent(suiteVersionKey)}/cases:add`, {
      jsonBody: { case_keys: caseKeys },
    });
  }

  async removeSuiteCases(suiteKey: string, suiteVersionKey: string, caseKeys: string[]): Promise<void> {
    await this.request('POST', `/suites/${encodeURIComponent(suiteKey)}/versions/${encodeURIComponent(suiteVersionKey)}/cases:remove`, {
      jsonBody: { case_keys: caseKeys },
    });
  }

  async listPlans(versionKey: string): Promise<Plan[]> {
    const data = await this.request<
      {
        plan_key: string;
        version_key: string;
        suite_version_key: string;
        name: string;
        description?: string | null;
        status: Plan['status'];
        created_at: string;
        updated_at: string;
        run_count: number;
        pass_rate?: number | null;
      }[]
    >('GET', `/plans${buildQuery({ version_key: versionKey })}`);
    return data.map((item) => toPlan(item));
  }

  async createPlan(payload: CreatePlanPayload): Promise<Plan> {
    const data = await this.request<{
      plan_key: string;
      version_key: string;
      suite_version_key: string;
      name: string;
      description?: string | null;
      status: Plan['status'];
      created_at: string;
      updated_at: string;
      run_count: number;
      pass_rate?: number | null;
    }>('POST', '/plans', {
      jsonBody: {
        version_key: payload.versionKey,
        suite_version_key: payload.suiteVersionKey,
        name: payload.name,
        description: payload.description,
      },
    });
    return toPlan(data);
  }

  async deletePlan(planKey: string): Promise<void> {
    await this.request('DELETE', `/plans/${encodeURIComponent(planKey)}`);
  }

  async getPlanDetail(planKey: string): Promise<{ plan: Plan; runs: Run[] }> {
    const data = await this.request<{
      plan: {
        plan_key: string;
        version_key: string;
        suite_version_key: string;
        name: string;
        description?: string | null;
        status: Plan['status'];
        created_at: string;
        updated_at: string;
      };
      runs: {
        run_key: string;
        plan_key: string;
        version_key: string;
        name: string;
        build_no?: string | null;
        environment?: string | null;
        status: Run['status'];
        created_at: string;
        started_at: string;
        finished_at?: string | null;
        pass_rate?: number | null;
        executed_cases: number;
        total_cases: number;
      }[];
    }>('GET', `/plans/${encodeURIComponent(planKey)}`);
    return {
      plan: toPlan({
        ...data.plan,
        run_count: data.runs.length,
        pass_rate: data.runs[0]?.pass_rate ?? null,
      }),
      runs: data.runs.map((item) => toRun(item)),
    };
  }

  async createRun(planKey: string, payload: CreateRunPayload): Promise<Run> {
    const data = await this.request<{
      run_key: string;
      plan_key: string;
      version_key: string;
      name: string;
      build_no?: string | null;
      environment?: string | null;
      status: Run['status'];
      created_at: string;
      started_at: string;
      finished_at?: string | null;
      pass_rate?: number | null;
      executed_cases: number;
      total_cases: number;
    }>('POST', `/plans/${encodeURIComponent(planKey)}/runs`, {
      jsonBody: {
        name: payload.name,
        build_no: payload.buildNo,
        environment: payload.environment,
        case_keys: payload.caseKeys,
      },
    });
    return toRun(data);
  }

  async listRuns(versionKey: string): Promise<Run[]> {
    const data = await this.request<
      {
        run_key: string;
        plan_key: string;
        version_key: string;
        name: string;
        build_no?: string | null;
        environment?: string | null;
        status: Run['status'];
        created_at: string;
        started_at: string;
        finished_at?: string | null;
        pass_rate?: number | null;
        executed_cases: number;
        total_cases: number;
      }[]
    >('GET', `/runs${buildQuery({ version_key: versionKey })}`);
    return data.map((item) => toRun(item));
  }

  async getLatestRun(versionKey: string): Promise<Run> {
    const data = await this.request<{
      run_key: string;
      plan_key: string;
      version_key: string;
      name: string;
      build_no?: string | null;
      environment?: string | null;
      status: Run['status'];
      created_at: string;
      started_at: string;
      finished_at?: string | null;
      pass_rate?: number | null;
      executed_cases: number;
      total_cases: number;
    }>('GET', `/runs/latest${buildQuery({ version_key: versionKey })}`);
    return toRun(data);
  }

  async getRunDetail(runKey: string): Promise<Run> {
    const data = await this.request<{
      run_key: string;
      plan_key: string;
      version_key: string;
      name: string;
      build_no?: string | null;
      environment?: string | null;
      status: Run['status'];
      created_at: string;
      started_at: string;
      finished_at?: string | null;
      pass_rate?: number | null;
      executed_cases: number;
      total_cases: number;
    }>('GET', `/runs/${encodeURIComponent(runKey)}`);
    return toRun(data);
  }

  async listRunCases(runKey: string, status?: RunCase['status'], keyword?: string): Promise<RunCase[]> {
    const data = await this.request<
      {
        run_case_key: string;
        case_key: string;
        title: string;
        module: string;
        steps: string;
        expected: string;
        status: RunCase['status'];
        last_updated_at: string;
        last_updated_by?: string | null;
      }[]
    >('GET', `/runs/${encodeURIComponent(runKey)}/cases${buildQuery({ status, keyword })}`);
    return data.map((item) => ({
      runCaseKey: item.run_case_key,
      caseKey: item.case_key,
      title: item.title,
      module: item.module,
      steps: item.steps,
      expected: item.expected,
      status: item.status,
      lastUpdatedAt: item.last_updated_at,
      lastUpdatedBy: item.last_updated_by ?? undefined,
    }));
  }

  async updateRunCaseStatus(payload: UpdateRunCaseStatusPayload): Promise<void> {
    await this.request('PUT', `/runs/${encodeURIComponent(payload.runKey)}/cases/${encodeURIComponent(payload.runCaseKey)}`, {
      jsonBody: {
        status: payload.status,
        remark: payload.remark,
        attachments: payload.attachments ?? [],
      },
    });
  }

  async listRunCaseHistory(runKey: string, runCaseKey: string): Promise<RunCaseHistory[]> {
    const data = await this.request<
      {
        id: number;
        status: RunCase['status'];
        remark?: string | null;
        operator: string;
        operated_at: string;
        attachments: { name: string; url: string; size?: number; mime?: string }[];
      }[]
    >('GET', `/runs/${encodeURIComponent(runKey)}/cases/${encodeURIComponent(runCaseKey)}/history`);
    return data.map((item) => ({
      id: String(item.id),
      status: item.status,
      remark: item.remark ?? undefined,
      operator: item.operator,
      operatedAt: item.operated_at,
      attachments: item.attachments ?? [],
    }));
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
        run_key: payload.runKey,
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
        repo_url?: string | null;
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
      repoUrl: item.repo_url ?? undefined,
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
      repo_url?: string | null;
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
        repo_url: payload.repoUrl,
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
      repoUrl: data.repo_url ?? undefined,
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
      repo_url?: string | null;
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
      repoUrl: data.repo_url ?? undefined,
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

  async getCicdRunLogs(runId: string, cursor: number, limit = 200): Promise<CicdRunLogChunk> {
    const data = await this.request<{
      run_id: string;
      status: CicdRun['status'];
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
      lines: string[];
      next_cursor: number;
      has_more: boolean;
    }>(
      'GET',
      `/cicd/runs/${encodeURIComponent(runId)}/logs${buildQuery({
        cursor: String(cursor),
        limit: String(limit),
      })}`,
    );

    return {
      runId: data.run_id,
      status: data.status,
      finishedAt: data.finished_at ?? undefined,
      stages: data.stages.map(toCicdStage),
      lines: data.lines,
      nextCursor: data.next_cursor,
      hasMore: data.has_more,
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
        report_archive_path?: string | null;
      }[]
    >('GET', `/automation/frameworks/${encodeURIComponent(frameworkKey)}/runs`);

    return data.map(toAutomationRun);
  }

  async getAutomationRunLogs(runId: string, cursor: number, limit = 200): Promise<AutomationRunLogChunk> {
    const data = await this.request<{
      run_id: string;
      status: AutomationRunStatus;
      finished_at?: string | null;
      report_archive_path?: string | null;
      lines: string[];
      next_cursor: number;
      has_more: boolean;
    }>(
      'GET',
      `/automation/runs/${encodeURIComponent(runId)}/logs${buildQuery({
        cursor: String(cursor),
        limit: String(limit),
      })}`,
    );

    return {
      runId: data.run_id,
      status: data.status,
      finishedAt: data.finished_at ?? undefined,
      reportArchivePath: data.report_archive_path ?? undefined,
      lines: data.lines,
      nextCursor: data.next_cursor,
      hasMore: data.has_more,
    };
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
      report_archive_path?: string | null;
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

  async cancelAutomationRun(runId: string): Promise<AutomationRun> {
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
      report_archive_path?: string | null;
    }>('POST', `/automation/runs/${encodeURIComponent(runId)}:cancel`);

    return toAutomationRun(data);
  }
}
