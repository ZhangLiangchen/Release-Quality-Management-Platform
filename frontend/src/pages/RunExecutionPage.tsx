import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Input,
  Row,
  Segmented,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { CASE_STATUS_COLOR, CASE_STATUS_LABEL } from '../domain/status';
import type { CaseStatus, Run, RunCase, RunCaseHistory } from '../domain/types';
import { useSession } from '../app/SessionContext';

const { Title, Text } = Typography;

type RunFilter = 'all' | CaseStatus;

const runFilterOptions: { label: string; value: RunFilter }[] = [
  { label: '全部', value: 'all' },
  { label: '未测', value: 'not_run' },
  { label: '通过', value: 'passed' },
  { label: '失败', value: 'failed' },
  { label: '阻塞', value: 'blocked' },
  { label: '跳过', value: 'skipped' },
];

const CASE_PAGE_SIZE = 10;

export function RunExecutionPage() {
  const { runKey } = useParams<{ runKey: string }>();
  const { repository } = useSession();
  const [runLoading, setRunLoading] = useState(false);
  const [casesLoading, setCasesLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [savingStatus, setSavingStatus] = useState(false);
  const [run, setRun] = useState<Run | null>(null);
  const [runCases, setRunCases] = useState<RunCase[]>([]);
  const [selectedRunCaseKey, setSelectedRunCaseKey] = useState<string | null>(null);
  const [history, setHistory] = useState<RunCaseHistory[]>([]);
  const [statusFilter, setStatusFilter] = useState<RunFilter>('all');
  const [keywordInput, setKeywordInput] = useState('');
  const [keywordQuery, setKeywordQuery] = useState('');
  const [casePage, setCasePage] = useState(1);
  const [statusValue, setStatusValue] = useState<CaseStatus>('not_run');
  const [remarkValue, setRemarkValue] = useState('');

  const selectedCase = useMemo(
    () => runCases.find((item) => item.runCaseKey === selectedRunCaseKey) ?? null,
    [runCases, selectedRunCaseKey],
  );

  const clampCasePage = (total: number, page: number) => {
    const maxPage = Math.max(1, Math.ceil(total / CASE_PAGE_SIZE));
    return Math.min(page, maxPage);
  };

  const loadRun = async (silent = false) => {
    if (!runKey) {
      return;
    }

    if (!silent) {
      setRunLoading(true);
    }
    try {
      const runInfo = await repository.getRunDetail(runKey);
      setRun(runInfo);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载计划执行详情失败');
    } finally {
      if (!silent) {
        setRunLoading(false);
      }
    }
  };

  const loadHistory = async (runCaseKey: string) => {
    if (!runKey) {
      return;
    }
    setHistoryLoading(true);
    try {
      const rows = await repository.listRunCaseHistory(runKey, runCaseKey);
      setHistory(rows);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载执行历史失败');
    } finally {
      setHistoryLoading(false);
    }
  };

  const loadCases = async (preferredCaseKey?: string | null) => {
    if (!runKey) {
      return;
    }
    setCasesLoading(true);
    try {
      const cases = await repository.listRunCases(
        runKey,
        statusFilter === 'all' ? undefined : statusFilter,
        keywordQuery || undefined,
      );
      setRunCases(cases);
      setCasePage((prev) => clampCasePage(cases.length, prev));

      const nextSelected =
        (preferredCaseKey && cases.some((item) => item.runCaseKey === preferredCaseKey) ? preferredCaseKey : undefined) ??
        (selectedRunCaseKey && cases.some((item) => item.runCaseKey === selectedRunCaseKey) ? selectedRunCaseKey : undefined) ??
        cases[0]?.runCaseKey ??
        null;

      setSelectedRunCaseKey(nextSelected);
      if (!nextSelected) {
        setHistory([]);
        return;
      }

      const selected = cases.find((item) => item.runCaseKey === nextSelected);
      if (selected) {
        setStatusValue(selected.status);
      }
      setRemarkValue('');
      await loadHistory(nextSelected);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载计划用例失败');
    } finally {
      setCasesLoading(false);
    }
  };

  useEffect(() => {
    void loadRun();
  }, [repository, runKey]);

  useEffect(() => {
    void loadCases();
  }, [repository, runKey, statusFilter, keywordQuery]);

  const applyKeywordSearch = () => {
    setCasePage(1);
    setKeywordQuery(keywordInput.trim());
  };

  const selectCase = async (nextRunCaseKey: string) => {
    setSelectedRunCaseKey(nextRunCaseKey);
    const target = runCases.find((item) => item.runCaseKey === nextRunCaseKey);
    if (target) {
      setStatusValue(target.status);
      setRemarkValue('');
    }
    await loadHistory(nextRunCaseKey);
  };

  const selectFirstCaseOnPage = (page: number) => {
    const firstCase = runCases[(page - 1) * CASE_PAGE_SIZE];
    if (!firstCase) {
      setSelectedRunCaseKey(null);
      setHistory([]);
      return;
    }
    if (firstCase.runCaseKey !== selectedRunCaseKey) {
      void selectCase(firstCase.runCaseKey);
    }
  };

  const saveStatus = async () => {
    if (!runKey || !selectedCase) {
      return;
    }
    setSavingStatus(true);
    try {
      await repository.updateRunCaseStatus({
        runKey,
        runCaseKey: selectedCase.runCaseKey,
        status: statusValue,
        remark: remarkValue,
      });
      message.success('执行状态已更新');
      setRemarkValue('');
      await Promise.all([loadRun(true), loadCases(selectedCase.runCaseKey)]);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存执行状态失败');
    } finally {
      setSavingStatus(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Title level={4} style={{ margin: 0 }}>
        计划执行页（{run?.name ?? runKey ?? '--'}）
      </Title>

      <Card loading={runLoading}>
        <Space wrap>
          <Tag color="blue">状态：{run?.status ?? '-'}</Tag>
          <Tag>版本：{run?.versionKey ?? '-'}</Tag>
          <Tag>进度：{run ? `${run.executedCases}/${run.totalCases}` : '-'}</Tag>
          <Tag>通过率：{run?.passRate == null ? '-' : `${(run.passRate * 100).toFixed(1)}%`}</Tag>
          <Text type="secondary">开始时间：{run?.startedAt ? new Date(run.startedAt).toLocaleString() : '-'}</Text>
        </Space>
      </Card>

      <Row gutter={16}>
        <Col xs={24} lg={10}>
          <Card title="计划用例列表">
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Segmented
                options={runFilterOptions}
                value={statusFilter}
                onChange={(value) => {
                  setCasePage(1);
                  setStatusFilter(value as RunFilter);
                }}
                block
              />
              <Space.Compact style={{ width: '100%' }}>
                <Input
                  placeholder="按编号/标题搜索"
                  value={keywordInput}
                  onChange={(event) => setKeywordInput(event.target.value)}
                  onPressEnter={applyKeywordSearch}
                />
                <Button onClick={applyKeywordSearch}>搜索</Button>
              </Space.Compact>

              <Table<RunCase>
                rowKey="runCaseKey"
                size="small"
                loading={casesLoading}
                pagination={{
                  pageSize: CASE_PAGE_SIZE,
                  current: casePage,
                  onChange: (page) => {
                    setCasePage(page);
                    selectFirstCaseOnPage(page);
                  },
                  showSizeChanger: false,
                }}
                dataSource={runCases}
                rowClassName={(record) => (record.runCaseKey === selectedRunCaseKey ? 'ant-table-row-selected' : '')}
                onRow={(record) => ({
                  onClick: () => {
                    void selectCase(record.runCaseKey);
                  },
                })}
                columns={[
                  {
                    title: '用例',
                    key: 'case',
                    render: (_, row) => (
                      <Space direction="vertical" size={0}>
                        <Text strong>{row.caseKey}</Text>
                        <Text type="secondary">{row.title}</Text>
                      </Space>
                    ),
                  },
                  {
                    title: '状态',
                    key: 'status',
                    width: 90,
                    render: (_, row) => (
                      <Tag color={CASE_STATUS_COLOR[row.status] === 'default' ? undefined : CASE_STATUS_COLOR[row.status]}>
                        {CASE_STATUS_LABEL[row.status]}
                      </Tag>
                    ),
                  },
                ]}
              />
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card title="用例详情">
            {!selectedCase ? (
              <Alert type="info" showIcon message="请选择左侧计划用例" />
            ) : (
              <Space direction="vertical" style={{ width: '100%' }} size={16}>
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label="用例编号">{selectedCase.caseKey}</Descriptions.Item>
                  <Descriptions.Item label="标题">{selectedCase.title}</Descriptions.Item>
                  <Descriptions.Item label="模块">{selectedCase.module}</Descriptions.Item>
                  <Descriptions.Item label="测试步骤">{selectedCase.steps}</Descriptions.Item>
                  <Descriptions.Item label="预期结果">{selectedCase.expected}</Descriptions.Item>
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
                    value={remarkValue}
                    placeholder="执行备注（失败/阻塞建议填写原因）"
                    onChange={(event) => setRemarkValue(event.target.value)}
                  />
                  <Button type="primary" loading={savingStatus} onClick={() => void saveStatus()}>
                    保存状态
                  </Button>
                </Space>

                <Table<RunCaseHistory>
                  rowKey="id"
                  size="small"
                  loading={historyLoading}
                  title={() => '最近执行历史（最近 10 条）'}
                  pagination={false}
                  dataSource={history}
                  columns={[
                    { title: '时间', dataIndex: 'operatedAt', key: 'operatedAt', width: 180, render: (v) => new Date(v).toLocaleString() },
                    { title: '执行人', dataIndex: 'operator', key: 'operator', width: 100 },
                    {
                      title: '结果',
                      dataIndex: 'status',
                      key: 'status',
                      width: 100,
                      render: (value: CaseStatus) => CASE_STATUS_LABEL[value],
                    },
                    { title: '备注', dataIndex: 'remark', key: 'remark', render: (value) => value || '-' },
                  ]}
                />
              </Space>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
