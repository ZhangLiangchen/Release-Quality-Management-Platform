import Papa from 'papaparse';
import type {
  CaseDetail,
  CaseWithStatus,
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
  UpdateCaseStatusPayload,
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
}
