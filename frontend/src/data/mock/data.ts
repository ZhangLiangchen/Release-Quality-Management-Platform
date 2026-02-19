import type {
  AutomationFramework,
  AutomationHypersonicRuntimeSettings,
  AutomationRun,
  CaseExecutionHistory,
  CaseTreeNode,
  CaseStatus,
  CicdPipeline,
  CicdRun,
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

function minutesAgo(minutes: number): string {
  return new Date(now.getTime() - minutes * 60 * 1000).toISOString();
}

export interface MockDatabase {
  config: ProjectConfig;
  users: User[];
  versions: Version[];
  caseTreeNodes: CaseTreeNode[];
  cases: TestCase[];
  versionCaseStatus: Record<string, Record<string, CaseStatus>>;
  caseHistory: CaseExecutionHistory[];
  issues: Issue[];
  cicdPipeline: CicdPipeline;
  cicdRuns: CicdRun[];
  automationFrameworks: AutomationFramework[];
  automationRuns: AutomationRun[];
  hypersonicRuntimeSettings: AutomationHypersonicRuntimeSettings;
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
    caseTreeNodes: [],
    cases: [],
    versionCaseStatus: {
      'v1.0.0': {},
      'v1.1.0': {},
    },
    caseHistory: [],
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
    cicdPipeline: {
      pipelineKey: 'hyperchain-binary',
      pipelineName: 'Hyperchain 二进制 CICD',
      projectName: 'Hyperchain',
      binaryName: 'hyperchain',
      buildMachine: {
        name: '内网构建机',
        ip: '172.22.67.76',
        note: '通过 SSH 在 /data/jinpeng/go-project-build 下执行分支目录创建与 git clone -b。',
      },
      deployTarget: {
        name: '制品分发机',
        ip: '10.10.131.192',
        note: '真实执行：构建机 scp 下发 + 目标机 SSH 校验 MD5',
      },
      buildScriptPath: '/opt/hyperchain/scripts/build_hyperchain.sh',
      artifactPath: '/opt/hyperchain/output/hyperchain',
      deployPath: '/home/hyperchain/dev_workspace/frigate-dynamic/bin_assets/new-hyperchain/hyperchain',
      stagesTemplate: [
        {
          stageKey: 'prepare',
          name: '拉取代码',
          description: '在构建机创建分支目录并执行 git clone -b。',
          command:
            'cd /data/jinpeng/go-project-build && mkdir -p {branch} && cd {branch} && git clone -b {branch} {repo_url} go-hyperchain',
        },
        {
          stageKey: 'build',
          name: '编译 Hyperchain 二进制',
          description: '在构建机执行编译脚本，生成可发布二进制。',
          command: 'ssh 172.22.67.76 "/opt/hyperchain/scripts/build_hyperchain.sh"',
        },
        {
          stageKey: 'package',
          name: '归档制品',
          description: '读取分支 HEAD、codeVersion 与构建机 MD5，并校验版本一致性。',
          command:
            'cd /data/jinpeng/go-project-build/{branch}/go-hyperchain && git rev-parse HEAD && git rev-parse --short=8 HEAD && ./hyperchain --codeVersion && md5sum ./hyperchain',
        },
        {
          stageKey: 'scp',
          name: 'SCP 分发二进制',
          description: '从构建机 scp 到目标机并进行双端 MD5 一致性校验。',
          command:
            'scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null /data/jinpeng/go-project-build/{branch}/go-hyperchain/hyperchain user@10.10.131.192:/home/hyperchain/dev_workspace/frigate-dynamic/bin_assets/new-hyperchain/hyperchain',
        },
      ],
      updatedAt: minutesAgo(30),
    },
    cicdRuns: [
      {
        runId: 'RUN-0001',
        pipelineKey: 'hyperchain-binary',
        pipelineName: 'Hyperchain 二进制 CICD',
        repoUrl: 'git@gitlab.example.com:hyperchain/go-hyperchain.git',
        branch: 'release/v1.0.0',
        commitId: 'placeholder-commit',
        note: '初始化占位流水线',
        status: 'running',
        triggeredBy: 'qa',
        startedAt: minutesAgo(20),
        stages: [
          {
            stageKey: 'prepare',
            name: '拉取代码',
            description: '在构建机创建分支目录并执行 git clone -b。',
            command:
              'cd /data/jinpeng/go-project-build && mkdir -p release/v1.0.0 && cd release/v1.0.0 && git clone -b release/v1.0.0 git@gitlab.example.com:hyperchain/go-hyperchain.git go-hyperchain',
            status: 'success',
            updatedAt: minutesAgo(18),
            note: '占位：代码拉取完成',
          },
          {
            stageKey: 'build',
            name: '编译 Hyperchain 二进制',
            description: '在构建机执行编译脚本，生成可发布二进制。',
            command: 'ssh 172.22.67.76 "/opt/hyperchain/scripts/build_hyperchain.sh"',
            status: 'running',
            updatedAt: minutesAgo(5),
            note: '占位：编译进行中',
          },
          {
            stageKey: 'package',
            name: '归档制品',
            description: '读取分支 HEAD、codeVersion 与构建机 MD5，并校验版本一致性。',
            command:
              'cd /data/jinpeng/go-project-build/release/v1.0.0/go-hyperchain && git rev-parse HEAD && git rev-parse --short=8 HEAD && ./hyperchain --codeVersion && md5sum ./hyperchain',
            status: 'pending',
          },
          {
            stageKey: 'scp',
            name: 'SCP 分发二进制',
            description: '从构建机 scp 到目标机并进行双端 MD5 一致性校验。',
            command:
              'scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null /data/jinpeng/go-project-build/release/v1.0.0/go-hyperchain/hyperchain user@10.10.131.192:/home/hyperchain/dev_workspace/frigate-dynamic/bin_assets/new-hyperchain/hyperchain',
            status: 'pending',
          },
        ],
        logs: [
          '[prepare] 在分支目录执行 git clone -b 完成（占位）',
          '[build] 执行 build_hyperchain.sh（占位）',
        ],
      },
    ],
    automationFrameworks: [
      {
        frameworkKey: 'frigateDynamic',
        entryName: '性能测试自动化',
        displayName: 'frigateDynamic',
        frameworkType: 'performance',
        description:
          'frigateDynamic 负责自动部署压力机上的 frigate 与被测 hyperchain 二进制，并通过 SSH 触发一次性压测作业。',
        streamlitUrl: 'http://10.10.131.192:8501',
        buildMachine: {
          name: '构建/调度机',
          ip: '10.10.131.192',
          note: '占位：后续补充 SSH 账号、脚本路径与网络策略',
        },
        deployTarget: {
          name: '被测集群入口',
          ip: '10.10.33.56',
          note: '占位：后续补充二进制下发目录、配置目录',
        },
        configurations: [
          {
            configKey: 'perf-default',
            name: '默认性能配置',
            description: '占位配置，用于演示在线编辑与保存',
            content: [
              'job_name: frigate_dynamic_perf',
              'pressure_host: 10.10.131.192',
              'target_cluster_host: 10.10.33.56',
              'frigate_package_path: /data/frigate/frigate.tar.gz',
              'hyperchain_binary_path: /data/hyperchain/bin/hyperchain',
              'ssh_user: placeholder_user',
              'ssh_port: 22',
            ].join('\n'),
            updatedAt: minutesAgo(12),
            updatedBy: 'qa',
          },
          {
            configKey: 'perf-long-run',
            name: '长稳压测配置',
            description: '用于长时压测的占位参数集',
            content: [
              'job_name: frigate_dynamic_long_run',
              'duration_min: 180',
              'rps: 1200',
              'pressure_host: 10.10.131.192',
              'target_cluster_host: 10.10.33.56',
            ].join('\n'),
            updatedAt: minutesAgo(50),
            updatedBy: 'admin',
          },
        ],
        testSuites: [
          {
            suiteKey: 'suite-perf-smoke',
            name: '性能冒烟套件',
            description: '快速验证部署与基本负载打通',
            content: ['suite: perf_smoke', 'scenario: basic_transfer', 'users: 50', 'duration_min: 10'].join('\n'),
            updatedAt: minutesAgo(11),
            updatedBy: 'qa',
          },
          {
            suiteKey: 'suite-perf-throughput',
            name: '吞吐压测套件',
            description: '压测吞吐与稳定性',
            content: ['suite: perf_throughput', 'scenario: tx_stress', 'users: 500', 'duration_min: 60'].join('\n'),
            updatedAt: minutesAgo(35),
            updatedBy: 'admin',
          },
        ],
        operationModes: [
          {
            mode: 'deploy_pressure_machine',
            label: '单独部署测试机',
            description: '仅在压力机部署或更新 frigate，不触发压测。',
          },
          {
            mode: 'deploy_hyperchain',
            label: '单独部署 Hyperchain',
            description: '仅向被测集群下发 hyperchain 二进制及配置。',
          },
          {
            mode: 'deploy_and_test',
            label: '一键部署及压测',
            description: '串行执行部署压力机、部署被测集群并触发压测。',
          },
          {
            mode: 'test_only',
            label: '仅执行压测',
            description: '跳过部署步骤，直接通过 SSH 触发 frigate 压测。',
          },
        ],
        updatedAt: minutesAgo(10),
      },
      {
        frameworkKey: 'hypersonic',
        entryName: '功能测试自动化',
        displayName: 'hypersonic',
        frameworkType: 'functional',
        description: 'hypersonic 用于执行功能回归自动化测试，支持配置与测试套在线维护和触发运行。',
        buildMachine: {
          name: '功能测试执行机',
          ip: '172.22.67.76',
          note: '占位：后续补充执行入口脚本与运行环境',
        },
        deployTarget: {
          name: '被测服务入口',
          ip: '10.10.33.56',
          note: '占位：后续补充服务地址、鉴权与环境变量',
        },
        configurations: [
          {
            configKey: 'func-default',
            name: '默认功能配置',
            description: '基础回归配置',
            content: [
              'suite_mode: full_regression',
              'target_env: testnet',
              'api_base_url: http://10.10.33.56:8080',
              'report_dir: /data/hypersonic/report',
            ].join('\n'),
            updatedAt: minutesAgo(40),
            updatedBy: 'qa',
          },
          {
            configKey: 'func-fast',
            name: '快速回归配置',
            description: '用于 CI 快速验证',
            content: ['suite_mode: smoke', 'target_env: testnet', 'parallelism: 4'].join('\n'),
            updatedAt: minutesAgo(55),
            updatedBy: 'admin',
          },
        ],
        testSuites: [
          {
            suiteKey: 'suite-func-core',
            name: '核心交易回归',
            description: '覆盖核心交易与账户流程',
            content: ['suite: core_tx', 'cases:', '- account/create', '- transfer/basic', '- transfer/rollback'].join(
              '\n',
            ),
            updatedAt: minutesAgo(33),
            updatedBy: 'qa',
          },
          {
            suiteKey: 'suite-func-contract',
            name: '合约功能回归',
            description: '覆盖合约部署、调用、升级流程',
            content: ['suite: contract_regression', 'cases:', '- contract/deploy', '- contract/invoke', '- contract/upgrade'].join(
              '\n',
            ),
            updatedAt: minutesAgo(80),
            updatedBy: 'admin',
          },
        ],
        operationModes: [
          {
            mode: 'functional_test',
            label: '执行功能测试',
            description: '按所选配置与测试套执行功能自动化测试。',
          },
        ],
        updatedAt: minutesAgo(30),
      },
    ],
    automationRuns: [
      {
        runId: 'AUTO-0001',
        frameworkKey: 'frigateDynamic',
        entryName: '性能测试自动化',
        configurationKey: 'perf-default',
        testSuiteKey: 'suite-perf-smoke',
        operationMode: 'deploy_and_test',
        status: 'running',
        note: '占位：夜间冒烟压测',
        triggeredBy: 'qa',
        startedAt: minutesAgo(9),
        logs: [
          '[deploy_pressure_machine] 占位：已连接压力机 10.10.131.192',
          '[deploy_hyperchain] 占位：已下发二进制到 10.10.33.56',
          '[test_only] 占位：已通过 SSH 启动 frigate 压测',
        ],
      },
      {
        runId: 'AUTO-0002',
        frameworkKey: 'hypersonic',
        entryName: '功能测试自动化',
        configurationKey: 'func-fast',
        testSuiteKey: 'suite-func-core',
        operationMode: 'functional_test',
        status: 'success',
        note: '占位：每日功能回归',
        triggeredBy: 'admin',
        startedAt: minutesAgo(120),
        finishedAt: minutesAgo(95),
        logs: ['[functional_test] 占位：执行 42 条用例，42 通过，0 失败'],
      },
    ],
    hypersonicRuntimeSettings: {
      liveEnabled: false,
      execContainerName: 'hypersonic_debug',
      executionRoute: 'local_exec',
      executionNote: '执行入口：本机 docker exec（固定容器：hypersonic_debug）',
    },
  };
}
