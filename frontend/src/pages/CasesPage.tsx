import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  Modal,
  Row,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Tree,
  Typography,
  Upload,
  message,
} from 'antd';
import type { DataNode } from 'antd/es/tree';
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useSession } from '../app/SessionContext';
import { CASE_STATUS_COLOR, CASE_STATUS_LABEL } from '../domain/status';
import type { CaseDetail, CaseStatus, ImportValidationResult, ModuleCaseGroup } from '../domain/types';
import { downloadBlob } from '../data';

const { Title, Text } = Typography;

type CaseFilter = 'all' | CaseStatus;

const caseFilterOptions: { label: string; value: CaseFilter }[] = [
  { label: '全部', value: 'all' },
  { label: '未测', value: 'not_run' },
  { label: '通过', value: 'passed' },
  { label: '失败', value: 'failed' },
  { label: '阻塞', value: 'blocked' },
  { label: '跳过', value: 'skipped' },
];

function toTreeData(groups: ModuleCaseGroup[]): DataNode[] {
  return groups.map((group) => ({
    title: (
      <Space>
        <Text strong>{group.module}</Text>
        <Text type="secondary">{group.cases.length}</Text>
      </Space>
    ),
    key: `module-${group.module}`,
    selectable: false,
    children: group.cases.map((item) => ({
      key: item.caseKey,
      title: (
        <Space size={8}>
          <Text>{item.caseKey}</Text>
          <Text>{item.title}</Text>
          <Tag color={CASE_STATUS_COLOR[item.latestStatus] === 'default' ? undefined : CASE_STATUS_COLOR[item.latestStatus]}>
            {CASE_STATUS_LABEL[item.latestStatus]}
          </Tag>
        </Space>
      ),
    })),
  }));
}

export function CasesPage() {
  const [searchParams] = useSearchParams();
  const { repository, viewVersionKey, user } = useSession();
  const [groups, setGroups] = useState<ModuleCaseGroup[]>([]);
  const [selectedCaseKey, setSelectedCaseKey] = useState<string | null>(null);
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<CaseFilter>((searchParams.get('status') as CaseFilter) ?? 'all');
  const [statusValue, setStatusValue] = useState<CaseStatus>('not_run');
  const [noteValue, setNoteValue] = useState('');
  const [users, setUsers] = useState<{ label: string; value: string }[]>([]);
  const [issueModalOpen, setIssueModalOpen] = useState(false);
  const [issueForm] = Form.useForm();
  const [validationResult, setValidationResult] = useState<ImportValidationResult | null>(null);

  const refreshCaseDetail = async (versionKey: string, caseKey: string) => {
    const caseDetail = await repository.getCaseDetail(versionKey, caseKey);
    setDetail(caseDetail);
    setStatusValue(caseDetail.caseInfo.latestStatus);
    setNoteValue('');
  };

  useEffect(() => {
    if (!viewVersionKey) {
      return;
    }

    const run = async () => {
      setLoading(true);
      try {
        const [nextGroups, nextUsers] = await Promise.all([
          repository.listCases(viewVersionKey),
          repository.listUsers(),
        ]);

        setGroups(nextGroups);
        setUsers(
          nextUsers
            .filter((item) => item.status === 'active')
            .map((item) => ({ label: item.username, value: item.userId })),
        );

        const allCases = nextGroups.flatMap((item) => item.cases);
        const firstCaseKey = allCases.at(0)?.caseKey;
        const existingCase = selectedCaseKey ? allCases.find((item) => item.caseKey === selectedCaseKey) : undefined;
        const targetCaseKey = existingCase?.caseKey ?? firstCaseKey ?? null;

        setSelectedCaseKey(targetCaseKey);
        if (targetCaseKey) {
          await refreshCaseDetail(viewVersionKey, targetCaseKey);
        } else {
          setDetail(null);
        }
      } catch (error) {
        message.error(error instanceof Error ? error.message : '加载用例失败');
      } finally {
        setLoading(false);
      }
    };

    void run();
  }, [repository, selectedCaseKey, viewVersionKey]);

  const filteredGroups = useMemo(() => {
    if (statusFilter === 'all') {
      return groups;
    }
    return groups
      .map((group) => ({
        ...group,
        cases: group.cases.filter((item) => item.latestStatus === statusFilter),
      }))
      .filter((group) => group.cases.length > 0);
  }, [groups, statusFilter]);

  const updateStatus = async () => {
    if (!viewVersionKey || !selectedCaseKey || !user) {
      return;
    }

    await repository.updateCaseStatus(
      {
        versionKey: viewVersionKey,
        caseKey: selectedCaseKey,
        status: statusValue,
        note: noteValue,
      },
      user,
    );

    message.success('状态更新成功');
    const [nextGroups] = await Promise.all([repository.listCases(viewVersionKey)]);
    setGroups(nextGroups);
    await refreshCaseDetail(viewVersionKey, selectedCaseKey);
  };

  const openIssueModal = () => {
    if (!viewVersionKey || !selectedCaseKey || !detail || !user) {
      return;
    }

    issueForm.setFieldsValue({
      title: `${detail.caseInfo.title} - 异常跟踪`,
      description: detail.caseInfo.steps,
      priority: 'high',
      severity: 'major',
      assigneeId: users[0]?.value,
    });
    setIssueModalOpen(true);
  };

  const createIssueFromCase = async () => {
    if (!viewVersionKey || !selectedCaseKey || !user) {
      return;
    }

    const values = await issueForm.validateFields();
    await repository.createIssue({
      title: values.title,
      description: values.description,
      priority: values.priority,
      severity: values.severity,
      assigneeId: values.assigneeId,
      reporterId: user.userId,
      foundVersionKey: viewVersionKey,
      links: [{ caseKey: selectedCaseKey, linkType: 'repro' }],
    });

    message.success('问题单创建成功');
    setIssueModalOpen(false);
  };

  const handleImportValidate = async (file: File) => {
    try {
      const result = await repository.validateImport('cases', file);
      setValidationResult(result);
      message.success('文件解析完成');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '导入预校验失败');
    }
  };

  const downloadTemplate = async () => {
    const blob = await repository.downloadTemplate('cases', 'csv');
    downloadBlob(blob, 'cases-template.csv');
  };

  const exportCases = async () => {
    if (!viewVersionKey) {
      return;
    }
    const blob = await repository.exportData('cases', 'xlsx', viewVersionKey);
    downloadBlob(blob, `cases-${viewVersionKey}.xlsx`);
  };

  const historyData = detail?.history.map((item) => ({
    key: item.id,
    executedAt: new Date(item.executedAt).toLocaleString(),
    executor: item.executorName,
    status: CASE_STATUS_LABEL[item.status],
    note: item.note ?? '-',
  }));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Row justify="space-between" align="middle">
        <Col>
          <Title level={4} style={{ margin: 0 }}>
            测试用例集（{viewVersionKey ?? '--'}）
          </Title>
        </Col>
        <Col>
          <Space>
            <Button onClick={downloadTemplate}>下载模板</Button>
            <Upload beforeUpload={(file) => {
              void handleImportValidate(file as File);
              return false;
            }} showUploadList={false}>
              <Button>导入预校验</Button>
            </Upload>
            <Button type="primary" onClick={exportCases}>
              导出 XLSX
            </Button>
          </Space>
        </Col>
      </Row>

      <Segmented
        options={caseFilterOptions}
        value={statusFilter}
        onChange={(value) => setStatusFilter(value as CaseFilter)}
      />

      <Row gutter={16}>
        <Col xs={24} lg={10}>
          <Card title="用例树" loading={loading}>
            <Tree
              treeData={toTreeData(filteredGroups)}
              selectedKeys={selectedCaseKey ? [selectedCaseKey] : []}
              onSelect={(keys) => {
                const selectedKey = keys[0];
                if (typeof selectedKey === 'string') {
                  setSelectedCaseKey(selectedKey);
                  if (viewVersionKey) {
                    void refreshCaseDetail(viewVersionKey, selectedKey);
                  }
                }
              }}
            />
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card title="用例详情" loading={loading}>
            {!detail ? (
              <Alert type="info" showIcon message="请选择左侧用例" />
            ) : (
              <Space direction="vertical" style={{ width: '100%' }} size={16}>
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label="用例 ID">{detail.caseInfo.caseKey}</Descriptions.Item>
                  <Descriptions.Item label="名称">{detail.caseInfo.title}</Descriptions.Item>
                  <Descriptions.Item label="模块">{detail.caseInfo.module}</Descriptions.Item>
                  <Descriptions.Item label="测试步骤">{detail.caseInfo.steps}</Descriptions.Item>
                  <Descriptions.Item label="预期结果">{detail.caseInfo.expected}</Descriptions.Item>
                </Descriptions>

                <Space direction="vertical" style={{ width: '100%' }}>
                  <Text strong>更新执行状态</Text>
                  <Segmented
                    block
                    options={[
                      { label: '未测', value: 'not_run' },
                      { label: '通过', value: 'passed' },
                      { label: '失败', value: 'failed' },
                      { label: '阻塞', value: 'blocked' },
                      { label: '跳过', value: 'skipped' },
                    ]}
                    value={statusValue}
                    onChange={(value) => setStatusValue(value as CaseStatus)}
                  />
                  <Input.TextArea
                    rows={3}
                    placeholder="执行备注（失败/阻塞建议填写原因）"
                    value={noteValue}
                    onChange={(event) => setNoteValue(event.target.value)}
                  />
                  <Space>
                    <Button type="primary" onClick={() => void updateStatus()}>
                      保存状态
                    </Button>
                    {(statusValue === 'failed' || statusValue === 'blocked') && (
                      <Button onClick={openIssueModal}>一键创建问题单</Button>
                    )}
                  </Space>
                </Space>

                <Table
                  size="small"
                  title={() => '最近执行历史（最近 10 条）'}
                  pagination={false}
                  dataSource={historyData}
                  columns={[
                    { title: '时间', dataIndex: 'executedAt', key: 'executedAt', width: 190 },
                    { title: '执行人', dataIndex: 'executor', key: 'executor', width: 100 },
                    { title: '结果', dataIndex: 'status', key: 'status', width: 100 },
                    { title: '备注', dataIndex: 'note', key: 'note' },
                  ]}
                />
              </Space>
            )}
          </Card>
        </Col>
      </Row>

      <Modal
        title="导入预校验结果"
        open={Boolean(validationResult)}
        onCancel={() => setValidationResult(null)}
        footer={null}
        width={760}
      >
        {validationResult && (
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Alert
              type={validationResult.errors.length > 0 ? 'warning' : 'success'}
              showIcon
              message={`总行数 ${validationResult.totalRows}，有效行 ${validationResult.validRows}，错误 ${validationResult.errors.length}`}
            />
            {validationResult.errors.length > 0 && (
              <Card size="small" title="错误明细">
                {validationResult.errors.map((error) => (
                  <div key={error}>{error}</div>
                ))}
              </Card>
            )}
            <Table
              size="small"
              pagination={false}
              dataSource={validationResult.preview.map((item, index) => ({ key: `${index}-${item.case_key ?? item.issue_key ?? 'row'}`, ...item }))}
              columns={Object.keys(validationResult.preview[0] ?? {}).map((key) => ({
                title: key,
                dataIndex: key,
                key,
              }))}
            />
          </Space>
        )}
      </Modal>

      <Modal
        title="从失败用例创建问题单"
        open={issueModalOpen}
        onCancel={() => setIssueModalOpen(false)}
        onOk={() => void createIssueFromCase()}
        okText="创建"
      >
        <Form layout="vertical" form={issueForm}>
          <Form.Item label="标题" name="title" rules={[{ required: true, message: '请输入标题' }]}>
            <Input />
          </Form.Item>
          <Form.Item label="描述" name="description" rules={[{ required: true, message: '请输入描述' }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item label="优先级" name="priority" rules={[{ required: true }]}>
            <Select
              options={[
                { label: '高', value: 'high' },
                { label: '中', value: 'medium' },
                { label: '低', value: 'low' },
              ]}
            />
          </Form.Item>
          <Form.Item label="严重程度" name="severity" rules={[{ required: true }]}>
            <Select
              options={[
                { label: '严重', value: 'critical' },
                { label: '主要', value: 'major' },
                { label: '轻微', value: 'minor' },
              ]}
            />
          </Form.Item>
          <Form.Item label="负责人" name="assigneeId">
            <Select allowClear options={users} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
