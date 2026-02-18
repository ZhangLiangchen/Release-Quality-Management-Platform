import { Alert, Button, Card, Space, Spin, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSession } from '../app/SessionContext';

const { Title, Text } = Typography;

export function CasesPage() {
  const navigate = useNavigate();
  const { repository, viewVersionKey } = useSession();
  const [loading, setLoading] = useState(true);
  const [latestRunKey, setLatestRunKey] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      if (!viewVersionKey) {
        setLoading(false);
        return;
      }
      try {
        const run = await repository.getLatestRun(viewVersionKey);
        setLatestRunKey(run.runKey);
      } catch (error) {
        message.error(error instanceof Error ? error.message : '未找到可用 Run');
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, [repository, viewVersionKey]);

  if (loading) {
    return <Spin />;
  }

  return (
    <Card>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Title level={4} style={{ margin: 0 }}>
          测试用例集已迁移
        </Title>
        <Alert
          showIcon
          type="info"
          message="/cases 已转为兼容入口"
          description="用例资产请在“用例库”维护，执行状态请在 Run 页面更新。"
        />
        {latestRunKey ? (
          <Space>
            <Button type="primary" onClick={() => navigate(`/runs/${latestRunKey}`)}>
              进入最新 Run
            </Button>
            <Button onClick={() => navigate('/case-library')}>进入用例库</Button>
            <Button onClick={() => navigate('/plans')}>进入测试计划</Button>
          </Space>
        ) : (
          <Text type="secondary">当前版本还没有可用 Run，请先在测试计划页面创建。</Text>
        )}
      </Space>
    </Card>
  );
}
