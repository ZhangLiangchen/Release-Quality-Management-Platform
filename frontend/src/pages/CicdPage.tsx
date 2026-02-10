import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Form,
  Input,
  Row,
  Space,
  Steps,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useSession } from '../app/SessionContext';
import type { CicdPipeline, CicdRun, CicdStage, CicdStageStatus } from '../domain/types';

const { Title, Text, Paragraph } = Typography;

const PIPELINE_KEY = 'hyperchain-binary';

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

export function CicdPage() {
  const { repository, user } = useSession();
  const [pipeline, setPipeline] = useState<CicdPipeline | null>(null);
  const [runs, setRuns] = useState<CicdRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [operatingStageKey, setOperatingStageKey] = useState<string | null>(null);
  const [triggerForm] = Form.useForm();

  const canOperate = user?.role !== 'viewer';

  const loadData = async () => {
    setLoading(true);
    try {
      const [nextPipeline, nextRuns] = await Promise.all([
        repository.getCicdPipeline(PIPELINE_KEY),
        repository.listCicdRuns(PIPELINE_KEY),
      ]);
      setPipeline(nextPipeline);
      setRuns(nextRuns);

      if (nextRuns.length === 0) {
        setSelectedRunId(null);
      } else if (!selectedRunId || !nextRuns.some((item) => item.runId === selectedRunId)) {
        setSelectedRunId(nextRuns[0].runId);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载 CICD 信息失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const selectedRun = useMemo(() => runs.find((item) => item.runId === selectedRunId) ?? null, [runs, selectedRunId]);

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
        branch: values.branch,
        commitId: values.commitId,
        note: values.note,
        triggeredBy: user.username,
      });
      message.success(`已触发流水线 ${created.runId}`);
      triggerForm.resetFields();
      await loadData();
      setSelectedRunId(created.runId);
    } catch (error) {
      if (error instanceof Error) {
        message.error(error.message);
      }
    }
  };

  const updateStage = async (stageKey: string, status: CicdStageStatus) => {
    if (!selectedRun) {
      return;
    }

    setOperatingStageKey(stageKey);
    try {
      const updatedRun = await repository.updateCicdStage({
        runId: selectedRun.runId,
        stageKey,
        status,
        note: `手动标记为 ${STAGE_STATUS_LABEL[status]}`,
      });

      setRuns((prev) => prev.map((item) => (item.runId === updatedRun.runId ? updatedRun : item)));
      message.success(`阶段 ${stageKey} 已更新为 ${STAGE_STATUS_LABEL[status]}`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '更新阶段状态失败');
    } finally {
      setOperatingStageKey(null);
    }
  };

  const runTableData = runs.map((item) => ({
    key: item.runId,
    runId: item.runId,
    branch: item.branch,
    status: item.status,
    triggeredBy: item.triggeredBy,
    startedAt: new Date(item.startedAt).toLocaleString(),
    finishedAt: item.finishedAt ? new Date(item.finishedAt).toLocaleString() : '-',
  }));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Title level={4} style={{ margin: 0 }}>
        CICD 流程（Hyperchain 二进制）
      </Title>

      <Alert
        type="warning"
        showIcon
        message="当前为占位流程：构建脚本路径、目标目录、机器凭据待你后续补充。"
      />

      <Row gutter={16}>
        <Col xs={24} xl={14}>
          <Card title="流水线配置" loading={loading}>
            {pipeline ? (
              <Descriptions bordered column={1} size="small">
                <Descriptions.Item label="流水线标识">{pipeline.pipelineKey}</Descriptions.Item>
                <Descriptions.Item label="项目/二进制">
                  {pipeline.projectName} / {pipeline.binaryName}
                </Descriptions.Item>
                <Descriptions.Item label="构建机">
                  {pipeline.buildMachine.name} ({pipeline.buildMachine.ip})
                  <br />
                  <Text type="secondary">{pipeline.buildMachine.note}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="目标机器">
                  {pipeline.deployTarget.name} ({pipeline.deployTarget.ip})
                  <br />
                  <Text type="secondary">{pipeline.deployTarget.note}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="构建脚本">{pipeline.buildScriptPath}</Descriptions.Item>
                <Descriptions.Item label="产物路径">{pipeline.artifactPath}</Descriptions.Item>
                <Descriptions.Item label="SCP 目标目录">{pipeline.deployPath}</Descriptions.Item>
              </Descriptions>
            ) : null}
          </Card>
        </Col>

        <Col xs={24} xl={10}>
          <Card title="触发 Hyperchain 流水线" loading={loading}>
            <Form form={triggerForm} layout="vertical" initialValues={{ branch: 'release/hyperchain-placeholder' }}>
              <Form.Item name="branch" label="分支" rules={[{ required: true, message: '请输入分支名称' }]}>
                <Input placeholder="例如 release/hyperchain-v1" />
              </Form.Item>
              <Form.Item name="commitId" label="Commit (可选)">
                <Input placeholder="占位：后续可接入真实 commit id" />
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

      <Card title="图形化流程操作" loading={loading}>
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
              <Card size="small" title={stage.name}>
                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                  <Tag color={STAGE_STATUS_COLOR[stage.status]}>{STAGE_STATUS_LABEL[stage.status]}</Tag>
                  <Paragraph style={{ marginBottom: 0 }}>
                    <Text type="secondary">{stage.description}</Text>
                  </Paragraph>
                  <Paragraph code style={{ marginBottom: 0, display: 'block', whiteSpace: 'normal' }}>
                    {stage.command}
                  </Paragraph>
                  <Space wrap>
                    <Button
                      size="small"
                      disabled={!canOperate || !selectedRun}
                      loading={operatingStageKey === stage.stageKey}
                      onClick={() => void updateStage(stage.stageKey, 'running')}
                    >
                      置为运行中
                    </Button>
                    <Button
                      size="small"
                      type="primary"
                      disabled={!canOperate || !selectedRun}
                      loading={operatingStageKey === stage.stageKey}
                      onClick={() => void updateStage(stage.stageKey, 'success')}
                    >
                      置为成功
                    </Button>
                    <Button
                      size="small"
                      danger
                      disabled={!canOperate || !selectedRun}
                      loading={operatingStageKey === stage.stageKey}
                      onClick={() => void updateStage(stage.stageKey, 'failed')}
                    >
                      置为失败
                    </Button>
                  </Space>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>

      <Card title="流水线运行记录" loading={loading}>
        <Table
          size="small"
          pagination={false}
          dataSource={runTableData}
          rowSelection={{
            type: 'radio',
            selectedRowKeys: selectedRunId ? [selectedRunId] : [],
            onChange: (selectedKeys) => {
              const next = selectedKeys[0];
              if (typeof next === 'string') {
                setSelectedRunId(next);
              }
            },
          }}
          columns={[
            { title: 'Run ID', dataIndex: 'runId', key: 'runId', width: 120 },
            { title: '分支', dataIndex: 'branch', key: 'branch', width: 220 },
            {
              title: '状态',
              dataIndex: 'status',
              key: 'status',
              width: 120,
              render: (status: CicdRun['status']) => (
                <Tag color={RUN_STATUS_COLOR[status]}>{RUN_STATUS_LABEL[status]}</Tag>
              ),
            },
            { title: '触发人', dataIndex: 'triggeredBy', key: 'triggeredBy', width: 120 },
            { title: '开始时间', dataIndex: 'startedAt', key: 'startedAt', width: 180 },
            { title: '结束时间', dataIndex: 'finishedAt', key: 'finishedAt', width: 180 },
          ]}
        />

        {selectedRun && (
          <Card title={`Run 日志 - ${selectedRun.runId}`} size="small" style={{ marginTop: 12 }}>
            <div style={{ maxHeight: 220, overflowY: 'auto', background: '#fafafa', padding: 12, borderRadius: 6 }}>
              {selectedRun.logs.length === 0 ? (
                <Text type="secondary">暂无日志</Text>
              ) : (
                selectedRun.logs.map((log) => (
                  <div key={log} style={{ fontFamily: 'Menlo, monospace', fontSize: 12 }}>
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
