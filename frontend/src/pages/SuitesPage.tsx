import {
  Button,
  Card,
  Col,
  Form,
  Input,
  Modal,
  Row,
  Space,
  Table,
  Tag,
  Tree,
  Typography,
  message,
} from 'antd';
import type { DataNode } from 'antd/es/tree';
import { useEffect, useMemo, useState } from 'react';
import { useSession } from '../app/SessionContext';
import type { CaseTreeNode, Suite, SuiteVersion, SuiteVersionDetail } from '../domain/types';

const { Title, Text } = Typography;

function versionStatusTag(status: SuiteVersion['status']) {
  if (status === 'published') {
    return <Tag color="green">已发布</Tag>;
  }
  return <Tag color="orange">草稿</Tag>;
}

function buildCaseTreeNodeMap(nodes: CaseTreeNode[]): Map<string, CaseTreeNode> {
  const map = new Map<string, CaseTreeNode>();
  const dfs = (items: CaseTreeNode[]) => {
    items.forEach((node) => {
      map.set(node.nodeId, node);
      dfs(node.children);
    });
  };
  dfs(nodes);
  return map;
}

function collectSubtreeCaseKeys(node: CaseTreeNode, collector: Set<string>) {
  node.cases.forEach((item) => collector.add(item.caseKey));
  node.children.forEach((child) => collectSubtreeCaseKeys(child, collector));
}

function toCaseTreeData(nodes: CaseTreeNode[]): DataNode[] {
  const toNode = (node: CaseTreeNode): DataNode => ({
    key: `node:${node.nodeId}`,
    title: node.name,
    children: [
      ...node.children.map((item) => toNode(item)),
      ...node.cases.map((item) => ({
        key: `case:${item.caseKey}`,
        title: `${item.caseKey} ${item.title}`,
      })),
    ],
  });

  return nodes.map((node) => toNode(node));
}

export function SuitesPage() {
  const { repository, viewVersionKey, user } = useSession();
  const [loading, setLoading] = useState(false);
  const [suites, setSuites] = useState<Suite[]>([]);
  const [selectedSuiteKey, setSelectedSuiteKey] = useState<string | null>(null);
  const [selectedSuiteVersionKey, setSelectedSuiteVersionKey] = useState<string | null>(null);
  const [detail, setDetail] = useState<SuiteVersionDetail | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [quickAddOpen, setQuickAddOpen] = useState(false);

  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(false);
  const [deletingSuite, setDeletingSuite] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [removingCaseKey, setRemovingCaseKey] = useState<string | null>(null);
  const [quickAddLoading, setQuickAddLoading] = useState(false);
  const [quickAdding, setQuickAdding] = useState(false);

  const [caseTree, setCaseTree] = useState<CaseTreeNode[]>([]);
  const [checkedTreeKeys, setCheckedTreeKeys] = useState<string[]>([]);

  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();

  const canEditSuite = user?.role === 'admin' || user?.role === 'qa';

  const loadSuiteDetail = async (suiteKey: string, suiteVersionKey: string) => {
    const nextDetail = await repository.getSuiteVersionDetail(suiteKey, suiteVersionKey);
    setDetail(nextDetail);
  };

  const loadSuites = async (preferred?: { suiteKey?: string | null; suiteVersionKey?: string | null }) => {
    if (!viewVersionKey) {
      return;
    }

    setLoading(true);
    try {
      const rows = await repository.listSuites(viewVersionKey);
      setSuites(rows);

      const candidateSuiteKey = preferred?.suiteKey ?? selectedSuiteKey;
      const targetSuiteKey = candidateSuiteKey && rows.some((item) => item.suiteKey === candidateSuiteKey)
        ? candidateSuiteKey
        : rows[0]?.suiteKey;

      const targetSuite = rows.find((item) => item.suiteKey === targetSuiteKey);
      const candidateVersionKey = preferred?.suiteVersionKey ?? selectedSuiteVersionKey;
      const targetVersionKey =
        candidateVersionKey && targetSuite?.versions.some((item) => item.suiteVersionKey === candidateVersionKey)
          ? candidateVersionKey
          : targetSuite?.versions[0]?.suiteVersionKey;

      setSelectedSuiteKey(targetSuiteKey ?? null);
      setSelectedSuiteVersionKey(targetVersionKey ?? null);

      if (targetSuiteKey && targetVersionKey) {
        await loadSuiteDetail(targetSuiteKey, targetVersionKey);
      } else {
        setDetail(null);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载用例集失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadSuites();
  }, [repository, viewVersionKey]);

  const currentSuite = useMemo(
    () => suites.find((item) => item.suiteKey === selectedSuiteKey) ?? null,
    [selectedSuiteKey, suites],
  );

  const isDraftEditable = detail?.suiteVersion.status === 'draft';

  const createSuite = async () => {
    if (!viewVersionKey) {
      return;
    }

    try {
      setCreating(true);
      const values = await createForm.validateFields();
      const created = await repository.createSuite({
        versionKey: viewVersionKey,
        name: String(values.name).trim(),
        description: String(values.description ?? '').trim() || undefined,
      });
      message.success('用例集创建成功');
      setCreateOpen(false);
      createForm.resetFields();

      const createdVersionKey = created.versions[0]?.suiteVersionKey ?? null;
      await loadSuites({ suiteKey: created.suiteKey, suiteVersionKey: createdVersionKey });
    } catch (error) {
      message.error(error instanceof Error ? error.message : '创建用例集失败');
    } finally {
      setCreating(false);
    }
  };

  const openEditSuite = () => {
    if (!currentSuite) {
      return;
    }

    editForm.setFieldsValue({
      name: currentSuite.name,
      description: currentSuite.description ?? '',
    });
    setEditOpen(true);
  };

  const submitEditSuite = async () => {
    if (!currentSuite) {
      return;
    }

    try {
      setEditing(true);
      const values = await editForm.validateFields();
      await repository.updateSuite({
        suiteKey: currentSuite.suiteKey,
        name: String(values.name).trim(),
        description: String(values.description ?? '').trim() || undefined,
      });
      message.success('用例集已更新');
      setEditOpen(false);
      await loadSuites({ suiteKey: currentSuite.suiteKey, suiteVersionKey: selectedSuiteVersionKey });
    } catch (error) {
      message.error(error instanceof Error ? error.message : '更新用例集失败');
    } finally {
      setEditing(false);
    }
  };

  const deleteSuite = async () => {
    if (!selectedSuiteKey || !selectedSuiteVersionKey) {
      return;
    }

    try {
      setDeletingSuite(true);
      await repository.deleteSuite(selectedSuiteKey, selectedSuiteVersionKey);
      message.success('用例集已删除');
      await loadSuites();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除用例集失败');
      throw error;
    } finally {
      setDeletingSuite(false);
    }
  };

  const publishVersion = async () => {
    if (!selectedSuiteKey || !selectedSuiteVersionKey) {
      return;
    }

    try {
      setPublishing(true);
      await repository.publishSuiteVersion(selectedSuiteKey, selectedSuiteVersionKey);
      message.success('版本已发布');
      await loadSuites({ suiteKey: selectedSuiteKey, suiteVersionKey: selectedSuiteVersionKey });
    } catch (error) {
      message.error(error instanceof Error ? error.message : '发布版本失败');
    } finally {
      setPublishing(false);
    }
  };

  const openQuickAdd = async () => {
    if (!viewVersionKey || !selectedSuiteKey || !selectedSuiteVersionKey) {
      return;
    }

    setQuickAddOpen(true);
    setCheckedTreeKeys([]);
    setQuickAddLoading(true);
    try {
      const rows = await repository.listCaseTree(viewVersionKey);
      setCaseTree(rows);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载用例树失败');
      setQuickAddOpen(false);
    } finally {
      setQuickAddLoading(false);
    }
  };

  const submitQuickAdd = async () => {
    if (!selectedSuiteKey || !selectedSuiteVersionKey) {
      return;
    }

    const nodeMap = buildCaseTreeNodeMap(caseTree);
    const selectedCaseKeys = new Set<string>();

    checkedTreeKeys.forEach((key) => {
      if (key.startsWith('case:')) {
        selectedCaseKeys.add(key.replace(/^case:/, ''));
        return;
      }
      if (key.startsWith('node:')) {
        const node = nodeMap.get(key.replace(/^node:/, ''));
        if (node) {
          collectSubtreeCaseKeys(node, selectedCaseKeys);
        }
      }
    });

    const caseKeys = Array.from(selectedCaseKeys).sort((a, b) => a.localeCompare(b, 'en'));
    if (caseKeys.length === 0) {
      message.warning('请至少勾选一个用例或场景节点');
      return;
    }

    try {
      setQuickAdding(true);
      await repository.addSuiteCases(selectedSuiteKey, selectedSuiteVersionKey, caseKeys);
      message.success(`已添加 ${caseKeys.length} 条用例`);
      setQuickAddOpen(false);
      setCheckedTreeKeys([]);
      await loadSuites({ suiteKey: selectedSuiteKey, suiteVersionKey: selectedSuiteVersionKey });
    } catch (error) {
      message.error(error instanceof Error ? error.message : '快捷添加用例失败');
    } finally {
      setQuickAdding(false);
    }
  };

  const removeSingleCase = async (caseKey: string) => {
    if (!selectedSuiteKey || !selectedSuiteVersionKey) {
      return;
    }

    try {
      setRemovingCaseKey(caseKey);
      await repository.removeSuiteCases(selectedSuiteKey, selectedSuiteVersionKey, [caseKey]);
      message.success(`已移除用例 ${caseKey}`);
      await loadSuites({ suiteKey: selectedSuiteKey, suiteVersionKey: selectedSuiteVersionKey });
    } catch (error) {
      message.error(error instanceof Error ? error.message : '移除用例失败');
      throw error;
    } finally {
      setRemovingCaseKey(null);
    }
  };

  const caseTreeData = useMemo(() => toCaseTreeData(caseTree), [caseTree]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Row justify="space-between" align="middle">
        <Col>
          <Title level={4} style={{ margin: 0 }}>
            用例集（{viewVersionKey ?? '--'}）
          </Title>
        </Col>
        <Col>
          <Space>
            <Button onClick={() => setCreateOpen(true)} disabled={!canEditSuite}>
              新增用例集
            </Button>
            <Button onClick={openEditSuite} disabled={!canEditSuite || !currentSuite}>
              编辑用例集
            </Button>
            <Button
              danger
              loading={deletingSuite}
              disabled={!canEditSuite || !selectedSuiteKey || !selectedSuiteVersionKey}
              onClick={() => {
                if (!currentSuite || !selectedSuiteVersionKey) {
                  return;
                }
                Modal.confirm({
                  title: `确认删除用例集 ${currentSuite.name}？`,
                  content: '若当前版本存在问题单绑定用例，或该用例集已被测试计划引用，系统会阻止删除。',
                  okText: '删除',
                  cancelText: '取消',
                  onOk: async () => {
                    await deleteSuite();
                  },
                });
              }}
            >
              删除用例集
            </Button>
            <Button
              onClick={openQuickAdd}
              disabled={!canEditSuite || !selectedSuiteKey || !selectedSuiteVersionKey || !isDraftEditable}
            >
              快捷添加用例
            </Button>
            <Button
              onClick={publishVersion}
              disabled={!canEditSuite || !selectedSuiteKey || !selectedSuiteVersionKey || detail?.suiteVersion.status === 'published'}
              loading={publishing}
              type="primary"
            >
              发布版本
            </Button>
          </Space>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col xs={24} lg={10}>
          <Card title="用例集列表" loading={loading}>
            <Table<Suite>
              rowKey="suiteKey"
              size="small"
              pagination={{ pageSize: 8 }}
              dataSource={suites}
              onRow={(record) => ({
                style: {
                  cursor: 'pointer',
                  backgroundColor: record.suiteKey === selectedSuiteKey ? '#e6f4ff' : undefined,
                  boxShadow: record.suiteKey === selectedSuiteKey ? 'inset 3px 0 0 #1677ff' : undefined,
                  fontWeight: record.suiteKey === selectedSuiteKey ? 600 : undefined,
                },
                onClick: () => {
                  const suiteVersionKey = record.versions[0]?.suiteVersionKey;
                  setSelectedSuiteKey(record.suiteKey);
                  setSelectedSuiteVersionKey(suiteVersionKey ?? null);
                  if (suiteVersionKey) {
                    void loadSuiteDetail(record.suiteKey, suiteVersionKey).catch((error) => {
                      message.error(error instanceof Error ? error.message : '加载用例集详情失败');
                    });
                  } else {
                    setDetail(null);
                  }
                },
              })}
              columns={[
                {
                  title: '名称',
                  dataIndex: 'name',
                  key: 'name',
                  render: (name: string, row) => (
                    <Space size={6}>
                      {row.suiteKey === selectedSuiteKey ? <Tag color="blue">已选中</Tag> : null}
                      <Text strong={row.suiteKey === selectedSuiteKey}>{name}</Text>
                    </Space>
                  ),
                },
                {
                  title: '最新版本',
                  key: 'latest',
                  render: (_, row) => {
                    const latest = row.versions[0];
                    if (!latest) {
                      return <Text type="secondary">无</Text>;
                    }
                    return (
                      <Space size={6}>
                        <Text>v{latest.verNo}</Text>
                        {versionStatusTag(latest.status)}
                      </Space>
                    );
                  },
                },
                { title: '更新时间', dataIndex: 'updatedAt', key: 'updatedAt', render: (v) => new Date(v).toLocaleString() },
              ]}
            />
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card title="用例集详情" loading={loading}>
            {!detail ? (
              <Text type="secondary">请选择左侧用例集查看详情</Text>
            ) : (
              <Space direction="vertical" style={{ width: '100%' }} size={12}>
                <Space>
                  <Text strong>{detail.name}</Text>
                  <Tag>v{detail.suiteVersion.verNo}</Tag>
                  {versionStatusTag(detail.suiteVersion.status)}
                  <Tag>用例 {detail.suiteVersion.caseCount}</Tag>
                </Space>
                <Text type="secondary">{detail.description || '无描述'}</Text>

                {currentSuite && currentSuite.versions.length > 1 && (
                  <Space wrap>
                    {currentSuite.versions.map((item) => (
                      <Button
                        key={item.suiteVersionKey}
                        size="small"
                        type={item.suiteVersionKey === selectedSuiteVersionKey ? 'primary' : 'default'}
                        onClick={() => {
                          setSelectedSuiteVersionKey(item.suiteVersionKey);
                          void loadSuiteDetail(currentSuite.suiteKey, item.suiteVersionKey).catch((error) => {
                            message.error(error instanceof Error ? error.message : '加载用例集详情失败');
                          });
                        }}
                      >
                        v{item.verNo}
                      </Button>
                    ))}
                  </Space>
                )}

                <Table
                  rowKey="caseKey"
                  size="small"
                  pagination={{ pageSize: 10 }}
                  dataSource={detail.cases}
                  columns={[
                    { title: '用例编号', dataIndex: 'caseKey', key: 'caseKey', width: 180 },
                    { title: '标题', dataIndex: 'title', key: 'title' },
                    { title: '模块', dataIndex: 'module', key: 'module', width: 200 },
                    {
                      title: '操作',
                      key: 'actions',
                      width: 120,
                      render: (_, record) => {
                        const disableByIssue = Boolean(record.issueLinked);
                        const disabled = !canEditSuite || !isDraftEditable || disableByIssue;
                        const disabledReason = disableByIssue
                          ? '已绑定问题单，不允许删除'
                          : (!isDraftEditable ? '已发布版本不可编辑' : undefined);

                        return (
                          <Button
                            size="small"
                            danger
                            title={disabledReason}
                            disabled={disabled}
                            loading={removingCaseKey === record.caseKey}
                            onClick={() => {
                              Modal.confirm({
                                title: `确认移除用例 ${record.caseKey}？`,
                                content: disableByIssue ? '该用例已绑定问题单，不允许删除。' : undefined,
                                okText: '删除',
                                cancelText: '取消',
                                okButtonProps: { disabled: disableByIssue },
                                onOk: async () => {
                                  if (disableByIssue) {
                                    return;
                                  }
                                  await removeSingleCase(record.caseKey);
                                },
                              });
                            }}
                          >
                            删除
                          </Button>
                        );
                      },
                    },
                  ]}
                />
              </Space>
            )}
          </Card>
        </Col>
      </Row>

      <Modal
        title="新增用例集"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => void createSuite()}
        okText="创建"
        confirmLoading={creating}
      >
        <Form form={createForm} layout="vertical">
          <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入名称' }]}>
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item label="描述" name="description">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="编辑用例集"
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={() => void submitEditSuite()}
        okText="保存"
        confirmLoading={editing}
      >
        <Form form={editForm} layout="vertical">
          <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入名称' }]}>
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item label="描述" name="description">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="快捷添加用例"
        open={quickAddOpen}
        onCancel={() => setQuickAddOpen(false)}
        onOk={() => void submitQuickAdd()}
        okText="提交"
        confirmLoading={quickAdding}
        width={760}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Text type="secondary">勾选目录/文件会自动包含其下全部用例。</Text>
          <Card size="small" loading={quickAddLoading}>
            <div style={{ maxHeight: 420, overflow: 'auto' }}>
              <Tree
                checkable
                autoExpandParent={false}
                treeData={caseTreeData}
                checkedKeys={checkedTreeKeys}
                onCheck={(checked) => {
                  if (Array.isArray(checked)) {
                    setCheckedTreeKeys(checked as string[]);
                    return;
                  }
                  setCheckedTreeKeys((checked.checked as string[]) ?? []);
                }}
              />
            </div>
          </Card>
          <Text type="secondary">已勾选 {checkedTreeKeys.length} 个节点</Text>
        </Space>
      </Modal>
    </div>
  );
}
