import { Button, Card, Form, Input, Modal, Select, Space, Table, Tag, Typography, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useSession } from '../app/SessionContext';

const { Title } = Typography;

export function SettingsPage() {
  const { repository, user, refreshBootstrap, versions } = useSession();
  const [projectName, setProjectName] = useState('');
  const [versionList, setVersionList] = useState(versions);
  const [userList, setUserList] = useState<{ userId: string; username: string; email: string; role: string; status: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingProjectName, setSavingProjectName] = useState(false);
  const [creatingVersion, setCreatingVersion] = useState(false);
  const [switchingVersionKey, setSwitchingVersionKey] = useState<string | null>(null);
  const [deletingVersionKey, setDeletingVersionKey] = useState<string | null>(null);
  const [newVersion, setNewVersion] = useState('');
  const [userModalOpen, setUserModalOpen] = useState(false);
  const [userForm] = Form.useForm();

  const canEditConfig = useMemo(() => user?.role === 'admin' || user?.role === 'qa', [user?.role]);
  const canManageVersions = canEditConfig;
  const canManageUsers = user?.role === 'admin';

  const loadData = async () => {
    setLoading(true);
    try {
      const [config, nextVersions, nextUsers] = await Promise.all([
        repository.getConfig(),
        repository.listVersions(),
        repository.listUsers(),
      ]);
      setProjectName(config.projectName);
      setVersionList(nextVersions);
      setUserList(
        nextUsers.map((item) => ({
          userId: item.userId,
          username: item.username,
          email: item.email,
          role: item.role,
          status: item.status,
        })),
      );
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载配置失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [repository]);

  const saveProjectName = async () => {
    if (!canEditConfig) {
      return;
    }
    setSavingProjectName(true);
    try {
      await repository.updateConfig(projectName.trim());
      message.success('项目名称已保存');
      await refreshBootstrap();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存项目名称失败');
    } finally {
      setSavingProjectName(false);
    }
  };

  const addVersion = async () => {
    if (!newVersion.trim()) {
      message.warning('请输入版本号');
      return;
    }
    setCreatingVersion(true);
    try {
      await repository.createVersion(newVersion.trim());
      setNewVersion('');
      message.success('版本创建成功');
      await loadData();
      await refreshBootstrap();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '新增版本失败');
    } finally {
      setCreatingVersion(false);
    }
  };

  const setCurrentVersion = async (versionKey: string) => {
    setSwitchingVersionKey(versionKey);
    try {
      await repository.setCurrentVersion(versionKey);
      message.success('系统默认版本已更新');
      await loadData();
      await refreshBootstrap();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '设置当前版本失败');
    } finally {
      setSwitchingVersionKey(null);
    }
  };

  const removeVersion = async (versionKey: string) => {
    setDeletingVersionKey(versionKey);
    try {
      await repository.deleteVersion(versionKey);
      message.success('版本已删除');
      await loadData();
      await refreshBootstrap();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除版本失败');
    } finally {
      setDeletingVersionKey(null);
    }
  };

  const createUser = async () => {
    const values = await userForm.validateFields();
    await repository.createUser(values);
    message.success('用户创建成功');
    userForm.resetFields();
    setUserModalOpen(false);
    await loadData();
  };

  const disableUser = async (userId: string) => {
    await repository.deleteUser(userId);
    message.success('用户已禁用');
    await loadData();
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Title level={4} style={{ margin: 0 }}>
        配置中心
      </Title>

      <Card title="基础配置" loading={loading}>
        <Space align="start">
          <Input
            style={{ width: 360 }}
            value={projectName}
            disabled={!canEditConfig}
            onChange={(event) => setProjectName(event.target.value)}
            placeholder="项目名称"
          />
          <Button type="primary" loading={savingProjectName} disabled={!canEditConfig} onClick={() => void saveProjectName()}>
            保存
          </Button>
        </Space>
      </Card>

      <Card title="版本管理" loading={loading} extra={!canManageVersions ? <Tag>只读</Tag> : null}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space>
            <Input
              style={{ width: 220 }}
              value={newVersion}
              disabled={!canManageVersions}
              placeholder="例如 v1.2.0"
              onChange={(event) => setNewVersion(event.target.value)}
            />
            <Button type="primary" loading={creatingVersion} disabled={!canManageVersions} onClick={() => void addVersion()}>
              新增版本
            </Button>
          </Space>

          <Table
            rowKey="versionKey"
            dataSource={versionList}
            pagination={false}
            columns={[
              { title: '版本号', dataIndex: 'versionKey', key: 'versionKey' },
              {
                title: '当前版本',
                key: 'isCurrent',
                render: (_, record) => (record.isCurrent ? <Tag color="green">当前</Tag> : '-'),
              },
              {
                title: '创建时间',
                key: 'createdAt',
                render: (_, record) => new Date(record.createdAt).toLocaleString(),
              },
              {
                title: '操作',
                key: 'actions',
                width: 240,
                render: (_, record) => (
                  <Space>
                    <Button
                      size="small"
                      loading={switchingVersionKey === record.versionKey}
                      disabled={!canManageVersions || record.isCurrent}
                      onClick={() => void setCurrentVersion(record.versionKey)}
                    >
                      设为当前
                    </Button>
                    <Button
                      size="small"
                      danger
                      loading={deletingVersionKey === record.versionKey}
                      disabled={!canManageVersions || record.isCurrent}
                      onClick={() => {
                        Modal.confirm({
                          title: `确认删除 ${record.versionKey}？`,
                          content: '若版本下已有用例执行记录或问题单，系统会阻止删除。',
                          onOk: async () => {
                            await removeVersion(record.versionKey);
                          },
                        });
                      }}
                    >
                      删除
                    </Button>
                  </Space>
                ),
              },
            ]}
          />
        </Space>
      </Card>

      <Card
        title="用户管理"
        loading={loading}
        extra={
          <Button type="primary" disabled={!canManageUsers} onClick={() => setUserModalOpen(true)}>
            新增用户
          </Button>
        }
      >
        <Table
          rowKey="userId"
          dataSource={userList}
          pagination={false}
          columns={[
            { title: '用户 ID', dataIndex: 'userId', key: 'userId', width: 120 },
            { title: '用户名', dataIndex: 'username', key: 'username', width: 120 },
            { title: '邮箱', dataIndex: 'email', key: 'email' },
            { title: '角色', dataIndex: 'role', key: 'role', width: 120 },
            {
              title: '状态',
              dataIndex: 'status',
              key: 'status',
              width: 100,
              render: (value: string) => (value === 'active' ? <Tag color="green">启用</Tag> : <Tag>禁用</Tag>),
            },
            {
              title: '操作',
              key: 'actions',
              width: 140,
              render: (_, record) => (
                <Button
                  size="small"
                  danger
                  disabled={!canManageUsers || record.status !== 'active'}
                  onClick={() => {
                    Modal.confirm({
                      title: `确认禁用用户 ${record.username}？`,
                      onOk: () => disableUser(record.userId),
                    });
                  }}
                >
                  禁用
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title="新增用户"
        open={userModalOpen}
        onCancel={() => setUserModalOpen(false)}
        onOk={() => void createUser()}
        okText="创建"
      >
        <Form layout="vertical" form={userForm} initialValues={{ role: 'qa' }}>
          <Form.Item label="用户名" name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input />
          </Form.Item>
          <Form.Item label="邮箱" name="email" rules={[{ required: true, message: '请输入邮箱' }]}>
            <Input />
          </Form.Item>
          <Form.Item label="角色" name="role" rules={[{ required: true, message: '请选择角色' }]}>
            <Select
              options={[
                { label: '管理员', value: 'admin' },
                { label: 'QA', value: 'qa' },
                { label: 'DEV', value: 'dev' },
                { label: 'Viewer', value: 'viewer' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
