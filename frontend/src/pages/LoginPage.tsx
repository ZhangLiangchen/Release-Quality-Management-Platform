import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Form, Input, Space, Typography } from 'antd';
import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useSession } from '../app/SessionContext';

const { Title, Paragraph, Text } = Typography;

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useSession();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fromPath = (location.state as { from?: string } | undefined)?.from ?? '/';

  const onFinish = async (values: { username: string; password: string }) => {
    setSubmitting(true);
    setError(null);
    try {
      await login(values);
      navigate(fromPath, { replace: true });
    } catch (e) {
      const message = e instanceof Error ? e.message : '登录失败';
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        background: 'linear-gradient(120deg, #f5f7fa 0%, #e4ecfb 100%)',
        padding: 16,
      }}
    >
      <Card style={{ width: 420, borderRadius: 12 }}>
        <Space direction="vertical" size={4} style={{ width: '100%', marginBottom: 20 }}>
          <Title level={3} style={{ marginBottom: 0 }}>
            软件质量管理平台
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            P0 演示版（Mock 数据）
          </Paragraph>
        </Space>

        {error && (
          <Alert
            type="error"
            showIcon
            message={error}
            style={{ marginBottom: 16 }}
          />
        )}

        <Form layout="vertical" onFinish={onFinish} initialValues={{ username: 'qa', password: 'password123' }}>
          <Form.Item label="用户名" name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="admin / qa / dev / viewer" />
          </Form.Item>
          <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="password123" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={submitting}>
            登录
          </Button>
        </Form>

        <Text type="secondary" style={{ display: 'block', marginTop: 12 }}>
          默认密码：password123
        </Text>
      </Card>
    </div>
  );
}
