import type {
  CaseExecutionHistory,
  CaseStatus,
  Issue,
  ProjectConfig,
  TestCase,
  User,
  Version,
} from '../../domain/types';

const now = new Date();

function daysAgo(days: number): string {
  return new Date(now.getTime() - days * 24 * 60 * 60 * 1000).toISOString();
}

export interface MockDatabase {
  config: ProjectConfig;
  users: User[];
  versions: Version[];
  cases: TestCase[];
  versionCaseStatus: Record<string, Record<string, CaseStatus>>;
  caseHistory: CaseExecutionHistory[];
  issues: Issue[];
}

export function createInitialMockDatabase(): MockDatabase {
  return {
    config: {
      projectName: '测试管理系统',
      currentVersionKey: 'v1.0.0',
    },
    users: [
      {
        userId: 'U-001',
        username: 'admin',
        email: 'admin@example.com',
        role: 'admin',
        status: 'active',
      },
      {
        userId: 'U-002',
        username: 'qa',
        email: 'qa@example.com',
        role: 'qa',
        status: 'active',
      },
      {
        userId: 'U-003',
        username: 'dev',
        email: 'dev@example.com',
        role: 'dev',
        status: 'active',
      },
      {
        userId: 'U-004',
        username: 'viewer',
        email: 'viewer@example.com',
        role: 'viewer',
        status: 'active',
      },
    ],
    versions: [
      {
        versionId: 'V-001',
        versionKey: 'v1.0.0',
        name: 'v1.0.0',
        isCurrent: true,
        createdAt: daysAgo(20),
      },
      {
        versionId: 'V-002',
        versionKey: 'v1.1.0',
        name: 'v1.1.0',
        isCurrent: false,
        createdAt: daysAgo(7),
      },
    ],
    cases: [
      {
        caseId: 'C-001',
        caseKey: 'TC-001',
        title: '用户登录成功',
        steps: '输入正确用户名与密码，点击登录按钮',
        expected: '跳转首页并展示用户信息',
        module: '用户登录',
        tags: ['登录', '核心流程'],
        status: 'active',
      },
      {
        caseId: 'C-002',
        caseKey: 'TC-002',
        title: '用户登录失败提示',
        steps: '输入错误密码并提交',
        expected: '提示密码错误且不可进入系统',
        module: '用户登录',
        tags: ['登录', '异常分支'],
        status: 'active',
      },
      {
        caseId: 'C-003',
        caseKey: 'TC-003',
        title: '用户创建成功',
        steps: '管理员新增用户并提交',
        expected: '列表出现新用户记录',
        module: '用户管理',
        tags: ['用户管理'],
        status: 'active',
      },
      {
        caseId: 'C-004',
        caseKey: 'TC-004',
        title: '角色权限校验',
        steps: 'DEV 访问配置中心',
        expected: '无权限入口不可见',
        module: '用户管理',
        tags: ['权限'],
        status: 'active',
      },
      {
        caseId: 'C-005',
        caseKey: 'TC-005',
        title: '数据导出 CSV',
        steps: '导出当前问题单列表',
        expected: '下载文件并包含筛选结果',
        module: '数据导出',
        tags: ['导出'],
        status: 'active',
      },
      {
        caseId: 'C-006',
        caseKey: 'TC-006',
        title: '附件上传成功',
        steps: '上传截图并保存状态更新',
        expected: '历史中可查看附件链接',
        module: '数据导出',
        tags: ['附件'],
        status: 'active',
      },
    ],
    versionCaseStatus: {
      'v1.0.0': {
        'TC-001': 'passed',
        'TC-002': 'failed',
        'TC-003': 'passed',
        'TC-004': 'blocked',
        'TC-005': 'not_run',
        'TC-006': 'skipped',
      },
      'v1.1.0': {
        'TC-001': 'not_run',
        'TC-002': 'not_run',
        'TC-003': 'not_run',
        'TC-004': 'not_run',
        'TC-005': 'not_run',
        'TC-006': 'not_run',
      },
    },
    caseHistory: [
      {
        id: 'H-001',
        versionKey: 'v1.0.0',
        caseKey: 'TC-001',
        status: 'passed',
        executorId: 'U-002',
        executorName: 'qa',
        executedAt: daysAgo(5),
        note: '核心登录流程通过',
        attachments: [],
      },
      {
        id: 'H-002',
        versionKey: 'v1.0.0',
        caseKey: 'TC-002',
        status: 'failed',
        executorId: 'U-002',
        executorName: 'qa',
        executedAt: daysAgo(4),
        note: '验证码校验异常',
        attachments: [
          {
            name: 'login-fail.png',
            url: '/uploads/mock/login-fail.png',
          },
        ],
      },
      {
        id: 'H-003',
        versionKey: 'v1.0.0',
        caseKey: 'TC-004',
        status: 'blocked',
        executorId: 'U-002',
        executorName: 'qa',
        executedAt: daysAgo(3),
        note: '环境依赖未就绪',
        attachments: [],
      },
      {
        id: 'H-004',
        versionKey: 'v1.0.0',
        caseKey: 'TC-006',
        status: 'skipped',
        executorId: 'U-002',
        executorName: 'qa',
        executedAt: daysAgo(2),
        note: '本轮版本不执行',
        attachments: [],
      },
    ],
    issues: [
      {
        issueId: 'I-001',
        issueKey: 'ISS-001',
        title: '登录验证码校验失败',
        description: '输入正确验证码后仍提示错误。',
        status: 'to_verify',
        priority: 'high',
        severity: 'major',
        assigneeId: 'U-003',
        assigneeName: 'dev',
        reporterId: 'U-002',
        reporterName: 'qa',
        foundVersionKey: 'v1.0.0',
        fixVersionKey: 'v1.0.0',
        verifyVersionKey: 'v1.1.0',
        createdAt: daysAgo(4),
        updatedAt: daysAgo(1),
        links: [
          { caseKey: 'TC-002', linkType: 'repro' },
          { caseKey: 'TC-002', linkType: 'regression' },
        ],
      },
      {
        issueId: 'I-002',
        issueKey: 'ISS-002',
        title: '权限边界提示文案错误',
        description: '无权限时提示文案与规范不一致。',
        status: 'closed',
        priority: 'medium',
        severity: 'minor',
        assigneeId: 'U-003',
        assigneeName: 'dev',
        reporterId: 'U-002',
        reporterName: 'qa',
        foundVersionKey: 'v1.0.0',
        fixVersionKey: 'v1.0.0',
        verifyVersionKey: 'v1.0.0',
        createdAt: daysAgo(6),
        updatedAt: daysAgo(2),
        links: [
          { caseKey: 'TC-004', linkType: 'repro' },
          { caseKey: 'TC-004', linkType: 'regression' },
        ],
      },
      {
        issueId: 'I-003',
        issueKey: 'ISS-003',
        title: '导出功能字段缺失',
        description: '导出的问题单缺少优先级字段。',
        status: 'new',
        priority: 'high',
        severity: 'major',
        assigneeId: 'U-003',
        assigneeName: 'dev',
        reporterId: 'U-002',
        reporterName: 'qa',
        foundVersionKey: 'v1.1.0',
        createdAt: daysAgo(1),
        updatedAt: daysAgo(1),
        links: [{ caseKey: 'TC-005', linkType: 'repro' }],
      },
    ],
  };
}
