import { LinkOutlined } from '@ant-design/icons';
import {
  Button,
  Card,
  Col,
  Input,
  Radio,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useSession } from '../app/SessionContext';
import type {
  AutomationFramework,
  AutomationHypersonicRuntimeSettings,
  AutomationOperationMode,
  AutomationRun,
  AutomationRunStatus,
} from '../domain/types';

const { Title, Text, Paragraph } = Typography;

const RUN_STATUS_LABEL: Record<AutomationRunStatus, string> = {
  pending: '待执行',
  running: '执行中',
  success: '成功',
  failed: '失败',
  canceled: '已取消',
};

const RUN_STATUS_COLOR: Record<AutomationRunStatus, string> = {
  pending: 'default',
  running: 'processing',
  success: 'success',
  failed: 'error',
  canceled: 'warning',
};

type HypersonicExecContainerMode = 'default' | 'custom' | 'empty';

const HYPERSONIC_DEFAULT_EXEC_CONTAINER = 'hypersonic_debug';

interface AutomationFrameworkPageProps {
  frameworkKey: AutomationFramework['frameworkKey'];
  defaultTitle: string;
}

const PREFERRED_DEFAULT_SELECTION: Partial<
  Record<AutomationFramework['frameworkKey'], { configKey?: string; suiteKey?: string }>
> = {
  frigateDynamic: {
    configKey: 'whole_config.toml',
    suiteKey: 'standard.toml',
  },
};

function toLocalTime(value?: string): string {
  if (!value) {
    return '-';
  }
  return new Date(value).toLocaleString();
}

export function AutomationFrameworkPage({ frameworkKey, defaultTitle }: AutomationFrameworkPageProps) {
  const { repository, user } = useSession();
  const [framework, setFramework] = useState<AutomationFramework | null>(null);
  const [runs, setRuns] = useState<AutomationRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  const [savingSuite, setSavingSuite] = useState(false);
  const [triggering, setTriggering] = useState(false);

  const [selectedConfigKey, setSelectedConfigKey] = useState<string | null>(null);
  const [selectedSuiteKey, setSelectedSuiteKey] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [operationMode, setOperationMode] = useState<AutomationOperationMode | null>(null);
  const [configContent, setConfigContent] = useState('');
  const [suiteContent, setSuiteContent] = useState('');
  const [runNote, setRunNote] = useState('');
  const [hypersonicRuntime, setHypersonicRuntime] = useState<AutomationHypersonicRuntimeSettings | null>(null);
  const [hypersonicLiveEnabled, setHypersonicLiveEnabled] = useState(false);
  const [hypersonicExecMode, setHypersonicExecMode] = useState<HypersonicExecContainerMode>('default');
  const [hypersonicCustomContainerName, setHypersonicCustomContainerName] = useState('');
  const [savingHypersonicRuntime, setSavingHypersonicRuntime] = useState(false);
  const logCursorByRunIdRef = useRef<Record<string, number>>({});
  const runLogContainerRef = useRef<HTMLDivElement | null>(null);

  const canOperate = user?.role !== 'viewer';

  const applyHypersonicRuntimeState = (settings: AutomationHypersonicRuntimeSettings) => {
    setHypersonicRuntime(settings);
    setHypersonicLiveEnabled(settings.liveEnabled);

    const containerName = settings.execContainerName.trim();
    if (!containerName) {
      setHypersonicExecMode('empty');
      setHypersonicCustomContainerName('');
      return;
    }

    if (containerName === HYPERSONIC_DEFAULT_EXEC_CONTAINER) {
      setHypersonicExecMode('default');
      setHypersonicCustomContainerName('');
      return;
    }

    setHypersonicExecMode('custom');
    setHypersonicCustomContainerName(containerName);
  };

  const loadData = async () => {
    setLoading(true);
    try {
      const [nextFramework, nextRuns, nextHypersonicRuntime] = await Promise.all([
        repository.getAutomationFramework(frameworkKey),
        repository.listAutomationRuns(frameworkKey),
        frameworkKey === 'hypersonic'
          ? repository.getHypersonicRuntimeSettings().catch((error) => {
              console.error(error);
              return null;
            })
          : Promise.resolve(null),
      ]);
      setFramework(nextFramework);
      setRuns(nextRuns);
      if (nextHypersonicRuntime) {
        applyHypersonicRuntimeState(nextHypersonicRuntime);
      } else {
        setHypersonicRuntime(null);
        setHypersonicLiveEnabled(false);
        setHypersonicExecMode('default');
        setHypersonicCustomContainerName('');
      }
      nextRuns.forEach((run) => {
        const previousCursor = logCursorByRunIdRef.current[run.runId] ?? 0;
        logCursorByRunIdRef.current[run.runId] = Math.max(previousCursor, run.logs.length);
      });

      setSelectedConfigKey((current) => {
        if (current && nextFramework.configurations.some((item) => item.configKey === current)) {
          return current;
        }
        const preferredConfigKey = PREFERRED_DEFAULT_SELECTION[nextFramework.frameworkKey]?.configKey;
        if (preferredConfigKey && nextFramework.configurations.some((item) => item.configKey === preferredConfigKey)) {
          return preferredConfigKey;
        }
        return nextFramework.configurations[0]?.configKey ?? null;
      });
      setSelectedSuiteKey((current) => {
        if (current && nextFramework.testSuites.some((item) => item.suiteKey === current)) {
          return current;
        }
        const preferredSuiteKey = PREFERRED_DEFAULT_SELECTION[nextFramework.frameworkKey]?.suiteKey;
        if (preferredSuiteKey && nextFramework.testSuites.some((item) => item.suiteKey === preferredSuiteKey)) {
          return preferredSuiteKey;
        }
        return nextFramework.testSuites[0]?.suiteKey ?? null;
      });
      setOperationMode((current) => {
        if (current && nextFramework.operationModes.some((item) => item.mode === current)) {
          return current;
        }
        return nextFramework.operationModes[0]?.mode ?? null;
      });
      setSelectedRunId((current) => {
        if (current && nextRuns.some((item) => item.runId === current)) {
          return current;
        }
        return nextRuns[0]?.runId ?? null;
      });
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载自动化配置失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [frameworkKey]);

  const selectedConfig = useMemo(
    () => framework?.configurations.find((item) => item.configKey === selectedConfigKey) ?? null,
    [framework, selectedConfigKey],
  );
  const selectedSuite = useMemo(
    () => framework?.testSuites.find((item) => item.suiteKey === selectedSuiteKey) ?? null,
    [framework, selectedSuiteKey],
  );
  const selectedRun = useMemo(() => runs.find((item) => item.runId === selectedRunId) ?? null, [runs, selectedRunId]);
  const isHypersonic = framework?.frameworkKey === 'hypersonic';
  const effectiveConfigKey = useMemo(() => {
    if (!framework) {
      return selectedConfigKey;
    }
    if (framework.frameworkKey === 'hypersonic') {
      return framework.configurations[0]?.configKey ?? selectedConfigKey;
    }
    return selectedConfigKey;
  }, [framework, selectedConfigKey]);

  useEffect(() => {
    setConfigContent(selectedConfig?.content ?? '');
  }, [selectedConfigKey, selectedConfig?.content]);

  useEffect(() => {
    setSuiteContent(selectedSuite?.content ?? '');
  }, [selectedSuiteKey, selectedSuite?.content]);

  useEffect(() => {
    const runId = selectedRun?.runId;
    if (!runId) {
      return undefined;
    }

    if (logCursorByRunIdRef.current[runId] === undefined) {
      logCursorByRunIdRef.current[runId] = selectedRun.logs.length;
    }

    let stopped = false;
    let pulling = false;
    const pullLogs = async () => {
      if (pulling || stopped) {
        return;
      }
      pulling = true;
      try {
        let continueFetch = true;
        while (!stopped && continueFetch) {
          const cursor = logCursorByRunIdRef.current[runId] ?? 0;
          const chunk = await repository.getAutomationRunLogs(runId, cursor, 400);
          if (stopped) {
            return;
          }
          logCursorByRunIdRef.current[runId] = chunk.nextCursor;
          setRuns((prev) =>
            prev.map((item) =>
              item.runId === runId
                ? {
                    ...item,
                    status: chunk.status,
                    finishedAt: chunk.finishedAt,
                    reportArchivePath: chunk.reportArchivePath,
                    logs: chunk.lines.length > 0 ? [...item.logs, ...chunk.lines] : item.logs,
                  }
                : item,
            ),
          );

          continueFetch = chunk.hasMore;
          if (chunk.lines.length === 0 && !chunk.hasMore) {
            continueFetch = false;
          }
        }
      } catch (error) {
        if (!stopped) {
          console.error(error);
        }
      } finally {
        pulling = false;
      }
    };

    void pullLogs();
    if (selectedRun.status !== 'running' && selectedRun.status !== 'pending') {
      return () => {
        stopped = true;
      };
    }

    const timer = window.setInterval(() => {
      void pullLogs();
    }, 1000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [repository, selectedRun?.runId, selectedRun?.status]);

  useEffect(() => {
    const container = runLogContainerRef.current;
    if (!container) {
      return;
    }
    container.scrollTop = container.scrollHeight;
  }, [selectedRunId, selectedRun?.logs.length]);

  const saveConfig = async () => {
    if (!framework || !selectedConfigKey || !user) {
      return;
    }

    setSavingConfig(true);
    try {
      const updated = await repository.saveAutomationConfiguration({
        frameworkKey: framework.frameworkKey,
        configKey: selectedConfigKey,
        content: configContent,
        updatedBy: user.username,
      });
      setFramework(updated);
      message.success('配置文件已保存');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存配置失败');
    } finally {
      setSavingConfig(false);
    }
  };
  const saveSuite = async () => {
    if (!framework || !selectedSuiteKey || !user) {
      return;
    }

    setSavingSuite(true);
    try {
      const updated = await repository.saveAutomationTestSuite({
        frameworkKey: framework.frameworkKey,
        suiteKey: selectedSuiteKey,
        content: suiteContent,
        updatedBy: user.username,
      });
      setFramework(updated);
      message.success('测试套已保存');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存测试套失败');
    } finally {
      setSavingSuite(false);
    }
  };

  const saveHypersonicRuntime = async () => {
    if (!canOperate) {
      return;
    }

    const execContainerName =
      hypersonicExecMode === 'default'
        ? HYPERSONIC_DEFAULT_EXEC_CONTAINER
        : hypersonicExecMode === 'custom'
          ? hypersonicCustomContainerName.trim()
          : '';

    if (hypersonicExecMode === 'custom' && !execContainerName) {
      message.warning('自定义容器名不能为空；如需清空请选择“空值”');
      return;
    }

    setSavingHypersonicRuntime(true);
    try {
      const updatedRuntime = await repository.updateHypersonicRuntimeSettings({
        liveEnabled: hypersonicLiveEnabled,
        execContainerName,
      });
      applyHypersonicRuntimeState(updatedRuntime);
      const nextFramework = await repository.getAutomationFramework('hypersonic');
      setFramework(nextFramework);
      message.success('Hypersonic 运行参数已更新');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '更新运行参数失败');
    } finally {
      setSavingHypersonicRuntime(false);
    }
  };

  const triggerRun = async () => {
    if (!framework || !selectedSuiteKey || !operationMode || !user) {
      message.warning('请先选择测试套与执行模式');
      return;
    }
    if (!effectiveConfigKey) {
      message.error('未找到可用配置，请联系管理员检查后端配置');
      return;
    }

    setTriggering(true);
    try {
      const created = await repository.triggerAutomationRun({
        frameworkKey: framework.frameworkKey,
        configurationKey: effectiveConfigKey,
        testSuiteKey: selectedSuiteKey,
        operationMode,
        note: runNote.trim() || undefined,
        triggeredBy: user.username,
      });
      logCursorByRunIdRef.current[created.runId] = created.logs.length;
      setRuns((prev) => [created, ...prev]);
      setSelectedRunId(created.runId);
      setRunNote('');
      message.success(`已触发任务 ${created.runId}`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '触发执行失败');
    } finally {
      setTriggering(false);
    }
  };

  const cancelRun = async () => {
    if (!selectedRun || !canOperate) {
      return;
    }
    if (selectedRun.status !== 'pending' && selectedRun.status !== 'running') {
      return;
    }

    try {
      const updated = await repository.cancelAutomationRun(selectedRun.runId);
      logCursorByRunIdRef.current[updated.runId] = updated.logs.length;
      setRuns((prev) =>
        prev.map((item) => {
          if (item.runId !== updated.runId) {
            return item;
          }
          return updated;
        }),
      );
      message.success(`已请求取消任务 ${selectedRun.runId}`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '取消任务失败');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <Title level={4} style={{ margin: 0 }}>
          {framework?.entryName ?? defaultTitle}
        </Title>
        {framework?.frameworkType === 'performance' && framework.streamlitUrl && (
          <Tooltip title={`打开 Streamlit: ${framework.streamlitUrl}`}>
            <Button icon={<LinkOutlined />} href={framework.streamlitUrl} target="_blank">
              Streamlit
            </Button>
          </Tooltip>
        )}
      </div>

      <Row gutter={16}>
        {!isHypersonic && (
          <Col xs={24} xl={12}>
            <Card title="Configuration 选择与在线编辑" loading={loading}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Select
                  value={selectedConfigKey ?? undefined}
                  onChange={setSelectedConfigKey}
                  options={(framework?.configurations ?? []).map((item) => ({
                    label: `${item.name} (${item.configKey})`,
                    value: item.configKey,
                  }))}
                />
                {selectedConfig && (
                  <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                    {selectedConfig.description} | 最近更新：{toLocalTime(selectedConfig.updatedAt)} by {selectedConfig.updatedBy}
                  </Paragraph>
                )}
                <Input.TextArea rows={14} value={configContent} onChange={(event) => setConfigContent(event.target.value)} />
                <Button
                  type="primary"
                  loading={savingConfig}
                  disabled={!canOperate || !selectedConfig}
                  onClick={() => void saveConfig()}
                >
                  保存配置文件
                </Button>
              </Space>
            </Card>
          </Col>
        )}

        <Col xs={24} xl={12}>
          <Card title="TestSuite 选择与在线编辑" loading={loading}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Select
                value={selectedSuiteKey ?? undefined}
                onChange={setSelectedSuiteKey}
                options={(framework?.testSuites ?? []).map((item) => ({
                  label: `${item.name} (${item.suiteKey})`,
                  value: item.suiteKey,
                }))}
              />
              {selectedSuite && (
                <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                  {selectedSuite.description} | 最近更新：{toLocalTime(selectedSuite.updatedAt)} by {selectedSuite.updatedBy}
                </Paragraph>
              )}
              <Input.TextArea rows={14} value={suiteContent} onChange={(event) => setSuiteContent(event.target.value)} />
              <Button type="primary" loading={savingSuite} disabled={!canOperate || !selectedSuite} onClick={() => void saveSuite()}>
                保存测试套
              </Button>
            </Space>
          </Card>
        </Col>
        {isHypersonic && (
          <Col xs={24} xl={12}>
            <Card title="Hypersonic 运行通道参数" loading={loading}>
              <Space direction="vertical" style={{ width: '100%' }} size={12}>
                <div>
                  <Text strong>HYPERSONIC_LIVE_ENABLED</Text>
                  <Radio.Group
                    style={{ display: 'block', marginTop: 8 }}
                    value={hypersonicLiveEnabled}
                    onChange={(event) => setHypersonicLiveEnabled(Boolean(event.target.value))}
                  >
                    <Space direction="vertical">
                      <Radio value={true}>true（走 SSH 远端执行）</Radio>
                      <Radio value={false}>false（走本地执行）</Radio>
                    </Space>
                  </Radio.Group>
                </div>

                <div>
                  <Text strong>HYPERSONIC_EXEC_CONTAINER_NAME</Text>
                  <Radio.Group
                    style={{ display: 'block', marginTop: 8 }}
                    value={hypersonicExecMode}
                    onChange={(event) => setHypersonicExecMode(event.target.value as HypersonicExecContainerMode)}
                  >
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Radio value="default">默认值：{HYPERSONIC_DEFAULT_EXEC_CONTAINER}</Radio>
                      <Radio value="custom">自定义容器名</Radio>
                      <Radio value="empty">空值</Radio>
                    </Space>
                  </Radio.Group>
                  {hypersonicExecMode === 'custom' && (
                    <Input
                      style={{ marginTop: 8 }}
                      value={hypersonicCustomContainerName}
                      onChange={(event) => setHypersonicCustomContainerName(event.target.value)}
                      placeholder="输入容器名，例如 hypersonic_debug 或其他容器"
                    />
                  )}
                </div>

                <Space>
                  <Button
                    type="primary"
                    loading={savingHypersonicRuntime}
                    disabled={!canOperate}
                    onClick={() => void saveHypersonicRuntime()}
                  >
                    应用运行参数
                  </Button>
                  {!canOperate && <Text type="secondary">Viewer 角色仅可查看，不可修改。</Text>}
                </Space>

                <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                  {`HYPERSONIC_LIVE_ENABLED：决定执行通道
true：走 SSH 远端执行
false：走本地执行
HYPERSONIC_EXEC_CONTAINER_NAME：决定是否在“已有容器”里执行，以及容器名是什么
有值：走 docker exec <container>
为空：在 LIVE=true 时走 docker run（每 run 独立容器）；在 LIVE=false 时当前实现会报配置错误`}
                </Paragraph>
                {hypersonicRuntime && (
                  <Text type="secondary">
                    当前后端解析：{hypersonicRuntime.executionNote}
                  </Text>
                )}
              </Space>
            </Card>
          </Col>
        )}
      </Row>

      <Card title="执行测试">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Radio.Group
            value={operationMode ?? undefined}
            onChange={(event) => setOperationMode(event.target.value as AutomationOperationMode)}
          >
            <Space direction="vertical">
              {(framework?.operationModes ?? []).map((mode) => (
                <Radio key={mode.mode} value={mode.mode}>
                  {mode.label}
                  <Text type="secondary">（{mode.description}）</Text>
                </Radio>
              ))}
            </Space>
          </Radio.Group>

          <Input.TextArea
            rows={2}
            value={runNote}
            onChange={(event) => setRunNote(event.target.value)}
            placeholder="执行备注（可选）"
          />

          <Button type="primary" loading={triggering} disabled={!canOperate} onClick={() => void triggerRun()}>
            执行测试
          </Button>
          {!canOperate && <Text type="secondary">Viewer 角色仅可查看，不可执行。</Text>}
        </Space>
      </Card>

      <Card title="执行记录" loading={loading}>
        <Table
          rowKey="runId"
          size="small"
          pagination={false}
          dataSource={runs}
          rowSelection={{
            type: 'radio',
            selectedRowKeys: selectedRunId ? [selectedRunId] : [],
            onChange: (keys) => {
              const target = keys[0];
              if (typeof target === 'string') {
                setSelectedRunId(target);
              }
            },
          }}
          columns={[
            { title: 'Run ID', dataIndex: 'runId', key: 'runId', width: 120 },
            ...(isHypersonic ? [] : [{ title: '配置', dataIndex: 'configurationKey', key: 'configurationKey', width: 150 }]),
            { title: '测试套', dataIndex: 'testSuiteKey', key: 'testSuiteKey', width: 170 },
            {
              title: '执行模式',
              dataIndex: 'operationMode',
              key: 'operationMode',
              width: 180,
              render: (value: AutomationOperationMode) => {
                const label = framework?.operationModes.find((item) => item.mode === value)?.label ?? value;
                return <Tag>{label}</Tag>;
              },
            },
            {
              title: '状态',
              dataIndex: 'status',
              key: 'status',
              width: 110,
              render: (value: AutomationRunStatus) => (
                <Tag color={RUN_STATUS_COLOR[value]}>{RUN_STATUS_LABEL[value]}</Tag>
              ),
            },
            { title: '触发人', dataIndex: 'triggeredBy', key: 'triggeredBy', width: 100 },
            {
              title: '开始时间',
              dataIndex: 'startedAt',
              key: 'startedAt',
              width: 180,
              render: (value: string) => toLocalTime(value),
            },
            {
              title: '结束时间',
              dataIndex: 'finishedAt',
              key: 'finishedAt',
              width: 180,
              render: (value?: string) => toLocalTime(value),
            },
          ]}
        />

        {selectedRun && (
          <Card
            title={`任务日志 - ${selectedRun.runId}`}
            size="small"
            style={{ marginTop: 12 }}
            extra={
              <Space>
                {selectedRun.reportArchivePath && (
                  <a href={selectedRun.reportArchivePath} target="_blank" rel="noreferrer">
                    下载报告
                  </a>
                )}
                {(selectedRun.status === 'pending' || selectedRun.status === 'running') && (
                  <Button danger size="small" disabled={!canOperate} onClick={() => void cancelRun()}>
                    取消任务
                  </Button>
                )}
              </Space>
            }
          >
            <div
              ref={runLogContainerRef}
              style={{ maxHeight: 220, overflowY: 'auto', background: '#fafafa', padding: 12, borderRadius: 6 }}
            >
              {selectedRun.logs.length === 0 ? (
                <Text type="secondary">暂无日志</Text>
              ) : (
                selectedRun.logs.map((log, index) => (
                  <div key={`${selectedRun.runId}-${index}`} style={{ fontFamily: 'Menlo, monospace', fontSize: 12 }}>
                    {log}
                  </div>
                ))
              )}
            </div>
          </Card>
        )}
      </Card>
    </div>
  );
}
