import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useSession } from '../app/SessionContext';
import { ISSUE_GROUP_LABEL, ISSUE_STATUS_LABEL } from '../domain/status';
import type { ImportValidationResult, Issue, IssueStatusGroup } from '../domain/types';
import { downloadBlob } from '../data';

const { Title } = Typography;

const groupOptions: IssueStatusGroup[] = ['all', 'open', 'pending', 'closed', 'invalid'];

const statusColors: Record<Issue['status'], string> = {
  new: 'processing',
  assigned: 'cyan',
  fixing: 'blue',
  to_verify: 'orange',
  verify_failed: 'red',
  closed: 'success',
  rejected: 'default',
  duplicate: 'default',
  invalid: 'default',
  deferred: 'default',
};

export function IssuesPage() {
  const [searchParams] = useSearchParams();
  const { repository, user, viewVersionKey, versions } = useSession();
  const [issues, setIssues] = useState<Issue[]>([]);
  const [users, setUsers] = useState<{ label: string; value: string }[]>([]);
  const [caseOptions, setCaseOptions] = useState<{ label: string; value: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusGroup, setStatusGroup] = useState<IssueStatusGroup>(
    (searchParams.get('status_group') as IssueStatusGroup) ?? 'all',
  );
  const [assigneeId, setAssigneeId] = useState<string | undefined>();
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [closeTargetIssue, setCloseTargetIssue] = useState<Issue | null>(null);
  const [validationResult, setValidationResult] = useState<ImportValidationResult | null>(null);
  const [createForm] = Form.useForm();
  const [closeForm] = Form.useForm();

  const loadIssues = async () => {
    if (!viewVersionKey) {
      return;
    }

    setLoading(true);
    try {
      const [nextIssues, nextUsers, caseGroups] = await Promise.all([
        repository.listIssues({ versionKey: viewVersionKey, statusGroup, assigneeId }),
        repository.listUsers(),
        repository.listCases(viewVersionKey),
      ]);
      setIssues(nextIssues);
      setUsers(nextUsers.filter((item) => item.status === 'active').map((item) => ({ label: item.username, value: item.userId })));
      setCaseOptions(
        caseGroups
          .flatMap((group) => group.cases)
          .map((item) => ({
            label: `${item.caseKey} - ${item.title}`,
            value: item.caseKey,
          })),
      );
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载问题单失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadIssues();
  }, [assigneeId, repository, statusGroup, viewVersionKey]);

  const createIssue = async () => {
    if (!viewVersionKey || !user) {
      return;
    }

    const values = await createForm.validateFields();
    await repository.createIssue({
      title: values.title,
      description: values.description,
      priority: values.priority,
      severity: values.severity,
      assigneeId: values.assigneeId,
      reporterId: user.userId,
      foundVersionKey: viewVersionKey,
      links: [{ caseKey: values.reproCaseKey, linkType: 'repro' }],
    });

    setCreateModalOpen(false);
    createForm.resetFields();
    message.success('问题单创建成功');
    await loadIssues();
  };

  const transitionIssue = async (issue: Issue, nextStatus: Issue['status']) => {
    await repository.transitionIssue(issue.issueKey, nextStatus);
    message.success('状态已更新');
    await loadIssues();
  };

  const closeIssue = async () => {
    if (!closeTargetIssue) {
      return;
    }
    const values = await closeForm.validateFields();
    await repository.closeIssue(closeTargetIssue.issueKey, {
      fixVersionKey: values.fixVersionKey,
      verifyVersionKey: values.verifyVersionKey,
      regressionCaseKeys: values.regressionCaseKeys,
    });
    message.success('问题单已关闭');
    setCloseTargetIssue(null);
    closeForm.resetFields();
    await loadIssues();
  };

  const downloadTemplate = async () => {
    const blob = await repository.downloadTemplate('issues', 'csv');
    downloadBlob(blob, 'issues-template.csv');
  };

  const exportIssues = async () => {
    if (!viewVersionKey) {
      return;
    }
    const blob = await repository.exportData('issues', 'xlsx', viewVersionKey);
    downloadBlob(blob, `issues-${viewVersionKey}.xlsx`);
  };

  const handleImportValidate = async (file: File) => {
    try {
      const result = await repository.validateImport('issues', file);
      setValidationResult(result);
      message.success('文件解析完成');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '导入预校验失败');
    }
  };

  const tabItems = useMemo(
    () =>
      groupOptions.map((group) => ({
        key: group,
        label: ISSUE_GROUP_LABEL[group],
      })),
    [],
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }} wrap>
        <Title level={4} style={{ margin: 0 }}>
          问题单（{viewVersionKey ?? '--'}）
        </Title>
        <Space>
          <Button onClick={downloadTemplate}>下载模板</Button>
          <Upload
            beforeUpload={(file) => {
              void handleImportValidate(file as File);
              return false;
            }}
            showUploadList={false}
          >
            <Button>导入预校验</Button>
          </Upload>
          <Button onClick={exportIssues}>导出 XLSX</Button>
          <Button type="primary" onClick={() => setCreateModalOpen(true)}>
            新建问题单
          </Button>
        </Space>
      </Space>

      <Card>
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
          <Tabs items={tabItems} activeKey={statusGroup} onChange={(key) => setStatusGroup(key as IssueStatusGroup)} />
          <Space>
            <span>负责人</span>
            <Select
              style={{ width: 220 }}
              allowClear
              placeholder="全部"
              value={assigneeId}
              options={users}
              onChange={(value) => setAssigneeId(value)}
            />
          </Space>
        </Space>
      </Card>

      <Card>
        <Table
          rowKey="issueKey"
          loading={loading}
          dataSource={issues}
          columns={[
            { title: 'ID', dataIndex: 'issueKey', key: 'issueKey', width: 120 },
            { title: '标题', dataIndex: 'title', key: 'title' },
            {
              title: '状态',
              dataIndex: 'status',
              key: 'status',
              width: 120,
              render: (value: Issue['status']) => <Tag color={statusColors[value]}>{ISSUE_STATUS_LABEL[value]}</Tag>,
            },
            {
              title: '优先级',
              dataIndex: 'priority',
              key: 'priority',
              width: 100,
              render: (value: string) => ({ high: '高', medium: '中', low: '低' }[value] ?? value),
            },
            {
              title: '负责人',
              key: 'assigneeName',
              width: 120,
              render: (_, record: Issue) => record.assigneeName ?? '-',
            },
            {
              title: '报告人',
              key: 'reporterName',
              width: 120,
              render: (_, record: Issue) => record.reporterName,
            },
            {
              title: '更新时间',
              key: 'updatedAt',
              width: 180,
              render: (_, record: Issue) => new Date(record.updatedAt).toLocaleString(),
            },
            {
              title: '操作',
              key: 'actions',
              width: 240,
              render: (_, record: Issue) => (
                <Space>
                  {['new', 'assigned', 'fixing', 'verify_failed'].includes(record.status) && (
                    <Button size="small" onClick={() => void transitionIssue(record, 'to_verify')}>
                      转待闭环
                    </Button>
                  )}
                  {record.status === 'to_verify' && (
                    <Button size="small" type="primary" onClick={() => {
                      setCloseTargetIssue(record);
                      closeForm.setFieldsValue({
                        fixVersionKey: record.fixVersionKey,
                        verifyVersionKey: record.verifyVersionKey,
                        regressionCaseKeys: record.links.filter((item) => item.linkType === 'regression').map((item) => item.caseKey),
                      });
                    }}>
                      关闭
                    </Button>
                  )}
                  {!['closed', 'invalid', 'rejected', 'duplicate', 'deferred'].includes(record.status) && (
                    <Button size="small" danger onClick={() => void transitionIssue(record, 'invalid')}>
                      作废
                    </Button>
                  )}
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title="新建问题单"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onOk={() => void createIssue()}
        okText="创建"
      >
        <Form layout="vertical" form={createForm} initialValues={{ priority: 'high', severity: 'major' }}>
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
          <Form.Item label="复现用例" name="reproCaseKey" rules={[{ required: true, message: '请选择复现用例' }]}>
            <Select options={caseOptions} showSearch optionFilterProp="label" />
          </Form.Item>
          <Form.Item label="负责人" name="assigneeId">
            <Select options={users} allowClear />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={closeTargetIssue ? `关闭问题单 ${closeTargetIssue.issueKey}` : '关闭问题单'}
        open={Boolean(closeTargetIssue)}
        onCancel={() => setCloseTargetIssue(null)}
        onOk={() => void closeIssue()}
        okText="确认关闭"
      >
        <Alert
          showIcon
          type="info"
          style={{ marginBottom: 12 }}
          message="关闭规则：必须填写修复版本、验证版本，并确保回归用例在验证版本下均为通过。"
        />
        <Form layout="vertical" form={closeForm}>
          <Form.Item label="修复版本" name="fixVersionKey" rules={[{ required: true, message: '请选择修复版本' }]}>
            <Select options={versions.map((item) => ({ label: item.versionKey, value: item.versionKey }))} />
          </Form.Item>
          <Form.Item label="验证版本" name="verifyVersionKey" rules={[{ required: true, message: '请选择验证版本' }]}>
            <Select options={versions.map((item) => ({ label: item.versionKey, value: item.versionKey }))} />
          </Form.Item>
          <Form.Item
            label="回归用例"
            name="regressionCaseKeys"
            rules={[{ required: true, message: '请选择至少一个回归用例' }]}
          >
            <Select mode="multiple" options={caseOptions} showSearch optionFilterProp="label" />
          </Form.Item>
        </Form>
      </Modal>

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
    </div>
  );
}
