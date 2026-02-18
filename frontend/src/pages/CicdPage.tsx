import {
  Button,
  Card,
  Col,
  Divider,
  Form,
  Input,
  Row,
  Steps,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSession } from '../app/SessionContext';
import type { CicdPipeline, CicdRun, CicdStage, CicdStageStatus } from '../domain/types';

const { Title, Text, Paragraph } = Typography;

const PIPELINE_KEY = 'hyperchain-binary';
const RUN_LIST_PAGE_SIZE = 10;

const STAGE_STATUS_LABEL: Record<CicdStageStatus, string> = {
  pending: '待执行',
  running: '执行中',
  success: '成功',
  failed: '失败',
};

const STAGE_STATUS_COLOR: Record<CicdStageStatus, string> = {
  pending: 'default',
  running: 'processing',
  success: 'success',
  failed: 'error',
};

const RUN_STATUS_LABEL: Record<CicdRun['status'], string> = {
  pending: '待执行',
  running: '执行中',
  success: '成功',
  failed: '失败',
};

const RUN_STATUS_COLOR: Record<CicdRun['status'], string> = {
  pending: 'default',
  running: 'processing',
  success: 'success',
  failed: 'error',
};

const STEP_STATUS_MAP: Record<CicdStageStatus, 'wait' | 'process' | 'finish' | 'error'> = {
  pending: 'wait',
  running: 'process',
  success: 'finish',
  failed: 'error',
};

function getCurrentStepIndex(stages: CicdStage[]): number {
  const runningIndex = stages.findIndex((item) => item.status === 'running');
  if (runningIndex >= 0) {
    return runningIndex;
  }

  const failedIndex = stages.findIndex((item) => item.status === 'failed');
  if (failedIndex >= 0) {
    return failedIndex;
  }

  const completedCount = stages.filter((item) => item.status === 'success').length;
  if (completedCount >= stages.length) {
    return stages.length - 1;
  }

  return completedCount;
}

function toLocalTime(value?: string): string {
  if (!value) {
    return '-';
  }
  return new Date(value).toLocaleString();
}

function formatStageCommand(command: string): string {
  return command.replace(/\s&&\s/g, ' &&\n');
}

export function CicdPage() {
  const { repository, user } = useSession();
  const [pipeline, setPipeline] = useState<CicdPipeline | null>(null);
  const [runs, setRuns] = useState<CicdRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [runListPage, setRunListPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [triggerForm] = Form.useForm();
  const logCursorByRunIdRef = useRef<Record<string, number>>({});
  const runLogContainerRef = useRef<HTMLDivElement | null>(null);

  const canOperate = user?.role !== 'viewer';

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [nextPipeline, nextRuns] = await Promise.all([
        repository.getCicdPipeline(PIPELINE_KEY),
        repository.listCicdRuns(PIPELINE_KEY),
      ]);
      setPipeline(nextPipeline);
      setRuns(nextRuns);
      nextRuns.forEach((run) => {
        const previousCursor = logCursorByRunIdRef.current[run.runId] ?? 0;
        logCursorByRunIdRef.current[run.runId] = Math.max(previousCursor, run.logs.length);
      });
      setSelectedRunId((previousSelectedRunId) => {
        if (nextRuns.length === 0) {
          return null;
        }
        if (!previousSelectedRunId || !nextRuns.some((item) => item.runId === previousSelectedRunId)) {
          return nextRuns[0].runId;
        }
        return previousSelectedRunId;
      });
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载 CICD 信息失败');
    } finally {
      setLoading(false);
    }
  }, [repository]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const selectedRun = useMemo(() => runs.find((item) => item.runId === selectedRunId) ?? null, [runs, selectedRunId]);
  const totalRunPages = useMemo(() => Math.max(1, Math.ceil(runs.length / RUN_LIST_PAGE_SIZE)), [runs.length]);
  const pagedRuns = useMemo(() => {
    const start = (runListPage - 1) * RUN_LIST_PAGE_SIZE;
    return runs.slice(start, start + RUN_LIST_PAGE_SIZE);
  }, [runs, runListPage]);

  useEffect(() => {
    if (runListPage > totalRunPages) {
      setRunListPage(totalRunPages);
    }
  }, [runListPage, totalRunPages]);

  useEffect(() => {
    if (runs.length === 0) {
      if (selectedRunId !== null) {
        setSelectedRunId(null);
      }
      return;
    }
    if (pagedRuns.length === 0) {
      return;
    }
    if (!selectedRunId || !pagedRuns.some((item) => item.runId === selectedRunId)) {
      setSelectedRunId(pagedRuns[0].runId);
    }
  }, [pagedRuns, runs.length, selectedRunId]);

  useEffect(() => {
    if (!selectedRun || selectedRun.status !== 'running') {
      return undefined;
    }

    const runId = selectedRun.runId;
    if (logCursorByRunIdRef.current[runId] === undefined) {
      logCursorByRunIdRef.current[runId] = selectedRun.logs.length;
    }

    let stopped = false;
    const pullLogs = async () => {
      const cursor = logCursorByRunIdRef.current[runId] ?? 0;
      try {
        const chunk = await repository.getCicdRunLogs(runId, cursor, 400);
        if (stopped) {
          return;
        }
        logCursorByRunIdRef.current[runId] = chunk.nextCursor;

        if (chunk.lines.length === 0 && chunk.status === 'running') {
          setRuns((prev) =>
            prev.map((item) =>
              item.runId === runId
                ? {
                    ...item,
                    status: chunk.status,
                    finishedAt: chunk.finishedAt,
                    stages: chunk.stages,
                  }
                : item,
            ),
          );
          return;
        }

        setRuns((prev) =>
          prev.map((item) => {
            if (item.runId !== runId) {
              return item;
            }
            return {
              ...item,
              status: chunk.status,
              finishedAt: chunk.finishedAt,
              stages: chunk.stages,
              logs: chunk.lines.length > 0 ? [...item.logs, ...chunk.lines] : item.logs,
            };
          }),
        );
      } catch (error) {
        if (!stopped) {
          // 不中断页面操作，只等待下一次轮询重试。
          console.error(error);
        }
      }
    };

    void pullLogs();
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

  const displayedStages = selectedRun
    ? selectedRun.stages
    : (pipeline?.stagesTemplate.map((item) => ({ ...item, status: 'pending' as const })) ?? []);

  const triggerRun = async () => {
    if (!user) {
      return;
    }

    try {
      const values = await triggerForm.validateFields();
      const created = await repository.triggerCicdRun({
        pipelineKey: PIPELINE_KEY,
        repoUrl: values.repoUrl,
        branch: values.branch,
        commitId: values.commitId,
        note: values.note,
        triggeredBy: user.username,
      });
      message.success(`已触发流水线 ${created.runId}`);
      triggerForm.resetFields();
      logCursorByRunIdRef.current[created.runId] = created.logs.length;
      setRuns((prev) => [created, ...prev.filter((item) => item.runId !== created.runId)]);
      setRunListPage(1);
      setSelectedRunId(created.runId);
    } catch (error) {
      if (error instanceof Error) {
        message.error(error.message);
      }
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Title level={4} style={{ margin: 0 }}>
        CICD 流程（Hyperchain 二进制）
      </Title>

      <Row gutter={16} align="stretch">
        <Col xs={24} xl={19} style={{ display: 'flex' }}>
          <Card title="图形化流程操作" loading={loading} style={{ width: '100%', height: '100%' }}>
            {displayedStages.length > 0 && (
              <Steps
                current={getCurrentStepIndex(displayedStages)}
                items={displayedStages.map((item) => ({
                  title: item.name,
                  description: item.description,
                  status: STEP_STATUS_MAP[item.status],
                }))}
              />
            )}

            <Divider style={{ margin: '16px 0' }} />

            <Row gutter={[12, 12]}>
              {displayedStages.map((stage) => (
                <Col xs={24} md={12} xl={6} key={stage.stageKey}>
                  <Card size="small" title={stage.name} style={{ height: '100%' }}>
                    <Tag color={STAGE_STATUS_COLOR[stage.status]} style={{ alignSelf: 'flex-start' }}>
                      {STAGE_STATUS_LABEL[stage.status]}
                    </Tag>
                    <Paragraph style={{ marginBottom: 6, marginTop: 6 }}>
                      <Text type="secondary">{stage.description}</Text>
                    </Paragraph>
                    <div
                      style={{
                        border: '1px solid #f0f0f0',
                        borderRadius: 8,
                        background: '#fafafa',
                        padding: '8px 10px',
                        height: 110,
                        overflowY: 'auto',
                        overflowX: 'hidden',
                      }}
                    >
                      <Text
                        code
                        style={{
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-all',
                          display: 'block',
                          lineHeight: '18px',
                        }}
                      >
                        {formatStageCommand(stage.command)}
                      </Text>
                    </div>
                  </Card>
                </Col>
              ))}
            </Row>
          </Card>
        </Col>

        <Col xs={24} xl={5} style={{ display: 'flex' }}>
          <Card title="触发 Hyperchain 流水线" loading={loading} style={{ width: '100%', height: '100%' }}>
            <Form form={triggerForm} layout="vertical">
              <Form.Item name="repoUrl" label="仓库地址" rules={[{ required: true, message: '请输入仓库地址' }]}>
                <Input placeholder="例如 git@gitlab.example.com:hyperchain/go-hyperchain.git" />
              </Form.Item>
              <Form.Item name="branch" label="分支" rules={[{ required: true, message: '请输入分支名称' }]}>
                <Input placeholder="例如 develop-bm-zkj-perf" />
              </Form.Item>
              <Form.Item name="commitId" label="Commit (可选)">
                <Input placeholder="可选：用于记录触发时对应 commit" />
              </Form.Item>
              <Form.Item name="note" label="备注 (可选)">
                <Input.TextArea rows={2} placeholder="例如：手工触发发布验证" />
              </Form.Item>

              <Button type="primary" block disabled={!canOperate} onClick={() => void triggerRun()}>
                触发流水线
              </Button>
              {!canOperate && <Text type="secondary">Viewer 角色仅可查看，不可操作。</Text>}
            </Form>
          </Card>
        </Col>
      </Row>

      <Card title="流水线运行记录" loading={loading}>
        <Table<CicdRun>
          size="small"
          rowKey="runId"
          dataSource={pagedRuns}
          locale={{ emptyText: '暂无运行记录' }}
          onRow={(record) => ({
            onClick: () => setSelectedRunId(record.runId),
            style: {
              cursor: 'pointer',
              backgroundColor: record.runId === selectedRunId ? '#f0f7ff' : undefined,
            },
          })}
          pagination={{
            current: runListPage,
            pageSize: RUN_LIST_PAGE_SIZE,
            total: runs.length,
            showSizeChanger: false,
            onChange: (page) => setRunListPage(page),
          }}
          columns={[
            { title: '运行编号', dataIndex: 'runId', key: 'runId', width: 140 },
            {
              title: '仓库',
              dataIndex: 'repoUrl',
              key: 'repoUrl',
              ellipsis: true,
              render: (value?: string) => value ?? '-',
            },
            { title: '分支', dataIndex: 'branch', key: 'branch', width: 220, ellipsis: true },
            { title: '触发人', dataIndex: 'triggeredBy', key: 'triggeredBy', width: 100 },
            {
              title: '开始时间',
              dataIndex: 'startedAt',
              key: 'startedAt',
              width: 180,
              render: (value?: string) => toLocalTime(value),
            },
            {
              title: '结束时间',
              dataIndex: 'finishedAt',
              key: 'finishedAt',
              width: 180,
              render: (value?: string) => toLocalTime(value),
            },
            {
              title: '运行状态',
              dataIndex: 'status',
              key: 'status',
              width: 120,
              render: (status: CicdRun['status']) => (
                <Tag color={RUN_STATUS_COLOR[status]}>{RUN_STATUS_LABEL[status]}</Tag>
              ),
            },
          ]}
        />

        {selectedRun && (
          <Card title={`Run 日志 - ${selectedRun.runId}`} size="small" style={{ marginTop: 12 }}>
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
