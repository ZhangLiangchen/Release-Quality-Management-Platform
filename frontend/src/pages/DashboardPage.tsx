import { Card, Col, Empty, Row, Table, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { KpiCard } from '../components/KpiCard';
import { ISSUE_STATUS_LABEL } from '../domain/status';
import type { DashboardKpi, Issue } from '../domain/types';
import { formatRate } from '../utils/metrics';
import { useSession } from '../app/SessionContext';

const { Title } = Typography;

export function DashboardPage() {
  const navigate = useNavigate();
  const { repository, viewVersionKey } = useSession();
  const [kpi, setKpi] = useState<DashboardKpi | null>(null);
  const [pendingIssues, setPendingIssues] = useState<Issue[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!viewVersionKey) {
      return;
    }

    const run = async () => {
      setLoading(true);
      try {
        const [nextKpi, nextPendingIssues] = await Promise.all([
          repository.getDashboard(viewVersionKey),
          repository.listPendingIssues(viewVersionKey),
        ]);
        setKpi(nextKpi);
        setPendingIssues(nextPendingIssues);
      } finally {
        setLoading(false);
      }
    };

    void run();
  }, [repository, viewVersionKey]);

  const pendingData = useMemo(
    () =>
      pendingIssues.map((item) => ({
        key: item.issueKey,
        issueKey: item.issueKey,
        title: item.title,
        status: ISSUE_STATUS_LABEL[item.status],
        assignee: item.assigneeName ?? '-',
        createdAt: new Date(item.createdAt).toLocaleString(),
      })),
    [pendingIssues],
  );

  if (!viewVersionKey) {
    return <Empty description="未选择版本" />;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Title level={4} style={{ margin: 0 }}>
        质量数据看板（{viewVersionKey}）
      </Title>

      <Row gutter={16}>
        <Col xs={24} md={8}>
          <KpiCard
            title="用例执行率"
            value={kpi ? formatRate(kpi.executionRate) : '--'}
            detail={kpi ? `${kpi.executedCases} / ${kpi.totalCases}` : '--'}
            onClick={() => navigate('/cases?status=not_run')}
          />
        </Col>
        <Col xs={24} md={8}>
          <KpiCard
            title="用例通过率（有效）"
            value={kpi ? formatRate(kpi.passRate) : '--'}
            detail={kpi ? `${kpi.passedCases} / ${kpi.executedCases - kpi.skippedCases}` : '--'}
            onClick={() => navigate('/cases?status=failed')}
          />
        </Col>
        <Col xs={24} md={8}>
          <KpiCard
            title="问题单闭环率"
            value={kpi ? formatRate(kpi.resolutionRate) : '--'}
            detail={kpi ? `${kpi.resolvedIssues} / ${kpi.totalIssues}` : '--'}
            onClick={() => navigate('/issues?status_group=pending')}
          />
        </Col>
      </Row>

      <Card title="待闭环问题单" loading={loading}>
        <Table
          dataSource={pendingData}
          pagination={false}
          locale={{ emptyText: '暂无待闭环问题单' }}
          columns={[
            { title: 'ID', dataIndex: 'issueKey', key: 'issueKey', width: 120 },
            { title: '标题', dataIndex: 'title', key: 'title' },
            { title: '状态', dataIndex: 'status', key: 'status', width: 120 },
            { title: '负责人', dataIndex: 'assignee', key: 'assignee', width: 120 },
            { title: '创建日期', dataIndex: 'createdAt', key: 'createdAt', width: 220 },
          ]}
        />
      </Card>
    </div>
  );
}
