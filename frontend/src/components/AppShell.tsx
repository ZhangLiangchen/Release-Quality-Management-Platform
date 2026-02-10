import { DashboardOutlined, SettingOutlined, BugOutlined, CheckSquareOutlined, LogoutOutlined } from '@ant-design/icons';
import { Button, Layout, Menu, Select, Space, Spin, Tag, Typography } from 'antd';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useSession } from '../app/SessionContext';

const { Header, Content } = Layout;
const { Text } = Typography;

const navItems = [
  { key: '/', label: '首页', icon: <DashboardOutlined /> },
  { key: '/cases', label: '测试用例集', icon: <CheckSquareOutlined /> },
  { key: '/issues', label: '问题单', icon: <BugOutlined /> },
  { key: '/settings', label: '配置中心', icon: <SettingOutlined /> },
];

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const { config, versions, user, logout, viewVersionKey, setViewVersion, bootstrapLoading } = useSession();

  const selectedKey = navItems.find((item) => {
    if (item.key === '/') {
      return location.pathname === '/';
    }
    return location.pathname.startsWith(item.key);
  })?.key;

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header
        style={{
          background: '#fff',
          padding: '0 24px',
          borderBottom: '1px solid #f0f0f0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16,
        }}
      >
        <Space size={16}>
          <Text strong style={{ fontSize: 18 }}>
            {config?.projectName ?? '软件质量管理平台'}
          </Text>
          <Menu
            mode="horizontal"
            selectedKeys={selectedKey ? [selectedKey] : []}
            items={navItems}
            onClick={({ key }) => navigate(key)}
            style={{ minWidth: 420, borderBottom: 'none' }}
          />
        </Space>

        <Space>
          <Text type="secondary">版本</Text>
          <Select
            style={{ width: 180 }}
            value={viewVersionKey ?? undefined}
            options={versions.map((item) => ({
              value: item.versionKey,
              label: `${item.versionKey}${item.isCurrent ? '（系统默认）' : ''}`,
            }))}
            onChange={setViewVersion}
          />
          <Tag color="blue">{user?.role?.toUpperCase()}</Tag>
          <Text>{user?.username}</Text>
          <Button type="text" icon={<LogoutOutlined />} onClick={logout}>
            退出
          </Button>
        </Space>
      </Header>

      <Content style={{ padding: 24 }}>
        {bootstrapLoading ? <Spin /> : <Outlet />}
      </Content>
    </Layout>
  );
}
