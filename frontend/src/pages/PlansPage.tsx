import {
  Button,
  Card,
  Col,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSession } from '../app/SessionContext';
import type { Plan, Run, Suite } from '../domain/types';

const { Title, Text } = Typography;

function planStatusTag(status: Plan['status']) {
  switch (status) {
    case 'done':
      return <Tag color="green">完成</Tag>;
    case 'archived':
      return <Tag>归档</Tag>;
    case 'draft':
      return <Tag color="orange">草稿</Tag>;
    default:
      return <Tag color="blue">进行中</Tag>;
  }
}

function runStatusTag(status: Run['status']) {
  if (status === 'success') {
    return <Tag color="green">成功</Tag>;
  }
  if (status === 'failed') {
    return <Tag color="red">失败</Tag>;
  }
  return <Tag color="blue">执行中</Tag>;
}

export function PlansPage() {
  const navigate = useNavigate();
  const { repository, viewVersionKey, user } = useSession();
  const [loading, setLoading] = useState(false);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [suites, setSuites] = useState<Suite[]>([]);
  const [selectedPlanKey, setSelectedPlanKey] = useState<string | null>(null);
  const [planRuns, setPlanRuns] = useState<Run[]>([]);
  const [deletingPlanKey, setDeletingPlanKey] = useState<string | null>(null);
  const [creatingRun, setCreatingRun] = useState(false);
  const [planForm] = Form.useForm();
  const [runForm] = Form.useForm();
  const canEditPlan = user?.role === 'admin' || user?.role === 'qa';

  const selectedPlan = useMemo(
    () => plans.find((item) => item.planKey === selectedPlanKey) ?? null,
    [plans, selectedPlanKey],
  );

  const loadData = async () => {
    if (!viewVersionKey) {
      return;
    }
    setLoading(true);
    try {
      const [planRows, suiteRows] = await Promise.all([
        repository.listPlans(viewVersionKey),
        repository.listSuites(viewVersionKey),
      ]);
      setPlans(planRows);
      setSuites(suiteRows);

      const targetPlanKey =
        selectedPlanKey && planRows.some((item) => item.planKey === selectedPlanKey)
          ? selectedPlanKey
          : planRows[0]?.planKey ?? null;
      setSelectedPlanKey(targetPlanKey);

      if (targetPlanKey) {
        const detail = await repository.getPlanDetail(targetPlanKey);
        setPlanRuns(detail.runs);
      } else {
        setPlanRuns([]);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载测试计划失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [repository, viewVersionKey]);

  const createPlan = async () => {
    if (!viewVersionKey) {
      return;
    }
    const values = await planForm.validateFields();
    await repository.createPlan({
      versionKey: viewVersionKey,
      suiteVersionKey: values.suiteVersionKey,
      name: String(values.name).trim(),
      description: String(values.description ?? '').trim() || undefined,
    });
    planForm.resetFields();
    message.success('测试计划创建成功');
    await loadData();
  };

  const createRun = async () => {
    if (!selectedPlanKey) {
      return;
    }
    setCreatingRun(true);
    try {
      const values = await runForm.validateFields();
      await repository.createRun(selectedPlanKey, {
        name: String(values.name).trim(),
        buildNo: String(values.buildNo ?? '').trim() || undefined,
        environment: String(values.environment ?? '').trim() || undefined,
      });
      runForm.resetFields();
      message.success('执行轮次创建成功');
      const detail = await repository.getPlanDetail(selectedPlanKey);
      setPlanRuns(detail.runs);
      await loadData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '创建执行轮次失败');
    } finally {
      setCreatingRun(false);
    }
  };

  const deletePlan = async (plan: Plan) => {
    try {
      setDeletingPlanKey(plan.planKey);
      await repository.deletePlan(plan.planKey);
      message.success('测试计划已删除');
      if (selectedPlanKey === plan.planKey) {
        setSelectedPlanKey(null);
        setPlanRuns([]);
      }
      await loadData();
    } catch (error) {
      const details =
        error && typeof error === 'object' && 'details' in error
          ? ((error as { details?: unknown }).details as { bindings?: { issue_key: string; case_key: string }[] } | undefined)
          : undefined;
      const bindings = details?.bindings ?? [];
      if (bindings.length > 0) {
        Modal.warning({
          title: '该测试计划有问题单绑定，不可删除',
          width: 720,
          okText: '我知道了',
          content: (
            <Table
              rowKey={(row) => `${row.issue_key}-${row.case_key}`}
              size="small"
              pagination={{ pageSize: 8 }}
              dataSource={bindings}
              columns={[
                { title: '问题单', dataIndex: 'issue_key', key: 'issue_key', width: 180 },
                { title: '对应用例', dataIndex: 'case_key', key: 'case_key' },
              ]}
            />
          ),
        });
      } else {
        message.error(error instanceof Error ? error.message : '删除测试计划失败');
      }
    } finally {
      setDeletingPlanKey(null);
    }
  };

  const suiteVersionOptions = suites
    .flatMap((suite) => suite.versions.map((version) => ({ suite, version })))
    .filter((item) => item.version.status === 'published')
    .map((item) => ({
      label: `${item.suite.name} / v${item.version.verNo}`,
      value: item.version.suiteVersionKey,
    }));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Title level={4} style={{ margin: 0 }}>
        测试计划（{viewVersionKey ?? '--'}）
      </Title>

      <Row gutter={16}>
        <Col xs={24} lg={10}>
          <Card title="创建测试计划">
            <Form form={planForm} layout="vertical">
              <Form.Item label="计划名称" name="name" rules={[{ required: true, message: '请输入计划名称' }]}>
                <Input maxLength={128} />
              </Form.Item>
              <Form.Item label="引用用例集版本" name="suiteVersionKey" rules={[{ required: true, message: '请选择已发布用例集版本' }]}>
                <Select options={suiteVersionOptions} />
              </Form.Item>
              <Form.Item label="描述" name="description">
                <Input.TextArea rows={3} />
              </Form.Item>
              <Button type="primary" onClick={() => void createPlan()}>
                创建计划
              </Button>
            </Form>
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card title="计划列表" loading={loading}>
            <Table<Plan>
              rowKey="planKey"
              size="small"
              pagination={{ pageSize: 8 }}
              dataSource={plans}
              onRow={(record) => ({
                onClick: () => {
                  setSelectedPlanKey(record.planKey);
                  void repository
                    .getPlanDetail(record.planKey)
                    .then((detail) => setPlanRuns(detail.runs))
                    .catch((error) => message.error(error instanceof Error ? error.message : '加载计划详情失败'));
                },
              })}
              columns={[
                { title: '计划名', dataIndex: 'name', key: 'name' },
                {
                  title: '状态',
                  key: 'status',
                  width: 100,
                  render: (_, row) => planStatusTag(row.status),
                },
                {
                  title: '执行次数',
                  dataIndex: 'runCount',
                  key: 'runCount',
                  width: 80,
                },
                {
                  title: '操作',
                  key: 'actions',
                  width: 100,
                  render: (_, row) => (
                    <Button
                      size="small"
                      danger
                      disabled={!canEditPlan}
                      loading={deletingPlanKey === row.planKey}
                      onClick={(event) => {
                        event.stopPropagation();
                        Modal.confirm({
                          title: `确认删除计划 ${row.name}？`,
                          content: '若计划中的用例已绑定问题单，系统会阻止删除并展示绑定详情。',
                          okText: '删除',
                          cancelText: '取消',
                          onOk: async () => {
                            await deletePlan(row);
                          },
                        });
                      }}
                    >
                      删除
                    </Button>
                  ),
                },
                {
                  title: '通过率',
                  key: 'passRate',
                  width: 100,
                  render: (_, row) => (row.passRate == null ? '-' : `${(row.passRate * 100).toFixed(1)}%`),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Card title={`计划执行历史${selectedPlan ? ` - ${selectedPlan.name}` : ''}`}>
        {!selectedPlan ? (
          <Text type="secondary">请选择计划后查看与创建执行轮次</Text>
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size={16}>
            <Form form={runForm} layout="inline">
              <Form.Item label="执行轮次名称" name="name" rules={[{ required: true, message: '请输入执行轮次名称' }]}>
                <Input style={{ width: 260 }} placeholder="例如：BM-L1-回归-轮次1" />
              </Form.Item>
              <Form.Item label="构建号" name="buildNo">
                <Input style={{ width: 160 }} placeholder="可选" />
              </Form.Item>
              <Form.Item label="环境" name="environment">
                <Input style={{ width: 160 }} placeholder="可选" />
              </Form.Item>
              <Button type="primary" loading={creatingRun} onClick={() => void createRun()}>
                创建执行轮次
              </Button>
            </Form>

            <Table<Run>
              rowKey="runKey"
              size="small"
              pagination={{ pageSize: 10 }}
              dataSource={planRuns}
              columns={[
                { title: '执行名称', dataIndex: 'name', key: 'name' },
                { title: '状态', key: 'status', width: 110, render: (_, row) => runStatusTag(row.status) },
                {
                  title: '进度',
                  key: 'progress',
                  width: 120,
                  render: (_, row) => `${row.executedCases}/${row.totalCases}`,
                },
                {
                  title: '通过率',
                  key: 'passRate',
                  width: 100,
                  render: (_, row) => (row.passRate == null ? '-' : `${(row.passRate * 100).toFixed(1)}%`),
                },
                {
                  title: '开始时间',
                  dataIndex: 'startedAt',
                  key: 'startedAt',
                  width: 180,
                  render: (value) => new Date(value).toLocaleString(),
                },
                {
                  title: '操作',
                  key: 'actions',
                  width: 100,
                  render: (_, row) => (
                    <Button type="link" onClick={() => navigate(`/runs/${row.runKey}`)}>
                      执行
                    </Button>
                  ),
                },
              ]}
            />
          </Space>
        )}
      </Card>
    </div>
  );
}
