import { PlusOutlined } from '@ant-design/icons';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Dropdown,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Tag,
  Tree,
  Typography,
  Upload,
  message,
} from 'antd';
import type { MenuProps } from 'antd';
import type { DataNode } from 'antd/es/tree';
import { useEffect, useMemo, useState } from 'react';
import { useSession } from '../app/SessionContext';
import type {
  CaseDetail,
  CaseTreeNode,
  ImportValidationResult,
} from '../domain/types';
import { downloadBlob } from '../data';

const { Title, Text } = Typography;

type TreeIndex = {
  nodeMap: Map<string, CaseTreeNode>;
  caseParentNodeIdMap: Map<string, string>;
  allCaseKeys: string[];
  selectableNodes: CaseTreeNode[];
};

type TreeViewNode = DataNode & {
  entityType: 'node' | 'case';
  node?: CaseTreeNode;
  caseKey?: string;
  caseTitle?: string;
};

function buildTreeIndex(nodes: CaseTreeNode[]): TreeIndex {
  const nodeMap = new Map<string, CaseTreeNode>();
  const caseParentNodeIdMap = new Map<string, string>();
  const allCaseKeys: string[] = [];
  const selectableNodes: CaseTreeNode[] = [];

  const dfs = (items: CaseTreeNode[]) => {
    items.forEach((node) => {
      nodeMap.set(node.nodeId, node);
      if (node.nodeType === 'directory' || node.nodeType === 'file') {
        selectableNodes.push(node);
      }
      node.cases.forEach((item) => {
        allCaseKeys.push(item.caseKey);
        caseParentNodeIdMap.set(item.caseKey, node.nodeId);
      });
      dfs(node.children);
    });
  };

  dfs(nodes);
  return { nodeMap, caseParentNodeIdMap, allCaseKeys, selectableNodes };
}

function filterTreeByKeyword(nodes: CaseTreeNode[], keyword: string): CaseTreeNode[] {
  const normalized = keyword.trim().toLowerCase();
  if (!normalized) {
    return nodes;
  }

  return nodes
    .map((node) => {
      const childMatches = filterTreeByKeyword(node.children, normalized);
      const caseMatches = node.cases.filter(
        (item) => item.caseKey.toLowerCase().includes(normalized) || item.title.toLowerCase().includes(normalized),
      );
      const selfMatch = node.name.toLowerCase().includes(normalized);
      if (selfMatch) {
        return {
          ...node,
          children: node.children,
          cases: node.cases,
        };
      }
      return {
        ...node,
        children: childMatches,
        cases: caseMatches,
      };
    })
    .filter((node) => node.children.length > 0 || node.cases.length > 0 || node.name.toLowerCase().includes(normalized));
}

function guessCaseKey(parent: CaseTreeNode): string {
  const token = parent.fullPath
    .split('/')
    .map((item) => item.replace(/[^A-Za-z0-9]/g, '').toUpperCase().slice(0, 4))
    .filter(Boolean)
    .slice(-3)
    .join('-');
  return `TC-${token || 'CASE'}-${Date.now().toString().slice(-4)}`;
}

function isFormValidationError(error: unknown): boolean {
  if (!error || typeof error !== 'object') {
    return false;
  }
  const maybe = error as { errorFields?: unknown };
  return Array.isArray(maybe.errorFields);
}

export function CaseLibraryPage() {
  const { repository, viewVersionKey, user } = useSession();
  const [tree, setTree] = useState<CaseTreeNode[]>([]);
  const [selectedCaseKey, setSelectedCaseKey] = useState<string | null>(null);
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [keywordInput, setKeywordInput] = useState('');
  const [keyword, setKeyword] = useState('');
  const [validationResult, setValidationResult] = useState<ImportValidationResult | null>(null);
  const [nodeModalOpen, setNodeModalOpen] = useState(false);
  const [caseModalOpen, setCaseModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [nodeSubmitting, setNodeSubmitting] = useState(false);
  const [caseSubmitting, setCaseSubmitting] = useState(false);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [actionNodeId, setActionNodeId] = useState<string | null>(null);
  const [nodeForm] = Form.useForm();
  const [caseForm] = Form.useForm();
  const [editForm] = Form.useForm();

  const canEditTree = user?.role === 'admin' || user?.role === 'qa';

  const refreshCaseDetail = async (versionKey: string, caseKey: string) => {
    const caseDetail = await repository.getCaseDetail(versionKey, caseKey);
    setDetail(caseDetail);
  };

  const loadTreeData = async (preferredCaseKey?: string | null) => {
    if (!viewVersionKey) {
      return;
    }

    setLoading(true);
    try {
      const nextTree = await repository.listCaseTree(viewVersionKey);
      setTree(nextTree);

      const treeIndex = buildTreeIndex(nextTree);
      const caseKeySet = new Set(treeIndex.allCaseKeys);
      const nextSelected =
        (preferredCaseKey && caseKeySet.has(preferredCaseKey) ? preferredCaseKey : undefined) ??
        (selectedCaseKey && caseKeySet.has(selectedCaseKey) ? selectedCaseKey : undefined) ??
        treeIndex.allCaseKeys.at(0) ??
        null;

      setSelectedCaseKey(nextSelected);
      if (nextSelected) {
        await refreshCaseDetail(viewVersionKey, nextSelected);
      } else {
        setDetail(null);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载用例树失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadTreeData();
  }, [repository, viewVersionKey]);

  const treeIndex = useMemo(() => buildTreeIndex(tree), [tree]);
  const displayedTree = useMemo(() => filterTreeByKeyword(tree, keyword), [tree, keyword]);
  const nodeMap = treeIndex.nodeMap;
  const actionNode = actionNodeId ? nodeMap.get(actionNodeId) ?? null : null;

  const nodeOptions = useMemo(
    () =>
      treeIndex.selectableNodes
        .map((node) => ({ label: node.fullPath, value: node.nodeId }))
        .sort((a, b) => a.label.localeCompare(b.label, 'zh-Hans-CN')),
    [treeIndex.selectableNodes],
  );

  const openAddDirectoryModal = (node: CaseTreeNode) => {
    setActionNodeId(node.nodeId);
    nodeForm.resetFields();
    setNodeModalOpen(true);
  };

  const openAddCaseModal = (node: CaseTreeNode) => {
    setActionNodeId(node.nodeId);
    caseForm.setFieldsValue({
      caseKey: guessCaseKey(node),
      title: '',
      steps: '',
      expected: '',
      tags: '',
    });
    setCaseModalOpen(true);
  };

  const openEditCaseModal = () => {
    if (!detail?.caseInfo) {
      return;
    }
    const parentNodeId = treeIndex.caseParentNodeIdMap.get(detail.caseInfo.caseKey) ?? undefined;
    editForm.setFieldsValue({
      parentNodeId,
      title: detail.caseInfo.title,
      steps: detail.caseInfo.steps,
      expected: detail.caseInfo.expected,
      tags: (detail.caseInfo.tags ?? []).join(','),
    });
    setEditModalOpen(true);
  };

  const treeData: DataNode[] = useMemo(() => {
    const toDataNode = (node: CaseTreeNode): TreeViewNode => ({
      key: `node:${node.nodeId}`,
      selectable: false,
      title: node.name,
      entityType: 'node',
      node,
      children: [
        ...node.children.map((item) => toDataNode(item)),
        ...node.cases.map((item): TreeViewNode => ({
          key: `case:${item.caseKey}`,
          title: `${item.caseKey} ${item.title}`,
          entityType: 'case',
          caseKey: item.caseKey,
          caseTitle: item.title,
        })),
      ],
    });

    return displayedTree.map((item) => toDataNode(item));
  }, [displayedTree]);

  const createDirectory = async () => {
    if (!viewVersionKey || !actionNode) {
      return;
    }
    try {
      setNodeSubmitting(true);
      const values = await nodeForm.validateFields();
      await repository.createCaseTreeNode({
        versionKey: viewVersionKey,
        parentNodeId: actionNode.nodeId,
        name: values.name,
        nodeType: 'directory',
      });
      message.success('目录创建成功');
      setNodeModalOpen(false);
      await loadTreeData(selectedCaseKey);
    } catch (error) {
      if (isFormValidationError(error)) {
        return;
      }
      message.error(error instanceof Error ? error.message : '目录创建失败');
    } finally {
      setNodeSubmitting(false);
    }
  };

  const createCase = async () => {
    if (!viewVersionKey || !actionNode) {
      return;
    }
    try {
      setCaseSubmitting(true);
      const values = await caseForm.validateFields();
      const caseKey = String(values.caseKey).trim();
      await repository.createCase({
        versionKey: viewVersionKey,
        parentNodeId: actionNode.nodeId,
        caseKey,
        title: String(values.title).trim(),
        steps: String(values.steps).trim(),
        expected: String(values.expected).trim(),
        tags: String(values.tags ?? '')
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
      });
      message.success('用例创建成功');
      setCaseModalOpen(false);
      await loadTreeData(caseKey);
    } catch (error) {
      if (isFormValidationError(error)) {
        return;
      }
      message.error(error instanceof Error ? error.message : '用例创建失败');
    } finally {
      setCaseSubmitting(false);
    }
  };

  const updateCase = async () => {
    if (!detail?.caseInfo) {
      return;
    }
    try {
      setEditSubmitting(true);
      const values = await editForm.validateFields();
      await repository.updateCase({
        caseKey: detail.caseInfo.caseKey,
        parentNodeId: values.parentNodeId,
        title: String(values.title).trim(),
        steps: String(values.steps).trim(),
        expected: String(values.expected).trim(),
        tags: String(values.tags ?? '')
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
      });
      message.success('用例更新成功');
      setEditModalOpen(false);
      await loadTreeData(detail.caseInfo.caseKey);
    } catch (error) {
      if (isFormValidationError(error)) {
        return;
      }
      message.error(error instanceof Error ? error.message : '用例更新失败');
    } finally {
      setEditSubmitting(false);
    }
  };

  const deleteCase = async () => {
    if (!detail?.caseInfo) {
      return;
    }
    try {
      await repository.deleteCase(detail.caseInfo.caseKey);
      message.success('用例已删除');
      await loadTreeData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '用例删除失败');
      throw error;
    }
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Row justify="space-between" align="middle">
        <Col>
          <Title level={4} style={{ margin: 0 }}>
            用例库（{viewVersionKey ?? '--'}）
          </Title>
        </Col>
        <Col>
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
            <Button type="primary" onClick={exportCases}>
              导出 XLSX
            </Button>
          </Space>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col xs={24} lg={10}>
          <Card title="用例树" loading={loading}>
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <Space.Compact style={{ width: '100%' }}>
                <Input
                  placeholder="按目录名、用例编号、标题搜索"
                  value={keywordInput}
                  onChange={(event) => setKeywordInput(event.target.value)}
                  onPressEnter={() => setKeyword(keywordInput.trim())}
                />
                <Button onClick={() => setKeyword(keywordInput.trim())}>搜索</Button>
                <Button onClick={() => { setKeywordInput(''); setKeyword(''); }}>清空</Button>
              </Space.Compact>

              <Tree
                treeData={treeData}
                virtual
                height={620}
                blockNode
                autoExpandParent={false}
                selectedKeys={selectedCaseKey ? [`case:${selectedCaseKey}`] : []}
                titleRender={(data) => {
                  const row = data as TreeViewNode;
                  if (row.entityType === 'case') {
                    return (
                      <Space size={8}>
                        <Text>{row.caseKey}</Text>
                        <Text>{row.caseTitle}</Text>
                      </Space>
                    );
                  }

                  const node = row.node;
                  if (!node) {
                    return <Text>{String(row.title ?? '')}</Text>;
                  }

                  const menuItems: MenuProps['items'] = [
                    ...(node.nodeType === 'directory' ? [{ key: 'add-directory', label: '新增目录' }] : []),
                    { key: 'add-case', label: '新增用例' },
                  ];

                  return (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, width: '100%' }}>
                      <Text strong={node.nodeType === 'directory'}>{node.name}</Text>
                      {canEditTree && (
                        <Dropdown
                          trigger={['click']}
                          menu={{
                            items: menuItems,
                            onClick: ({ key }) => {
                              if (key === 'add-directory') {
                                openAddDirectoryModal(node);
                              }
                              if (key === 'add-case') {
                                openAddCaseModal(node);
                              }
                            },
                          }}
                        >
                          <Button
                            type="text"
                            size="small"
                            icon={<PlusOutlined />}
                            onClick={(event) => event.stopPropagation()}
                          />
                        </Dropdown>
                      )}
                    </div>
                  );
                }}
                onSelect={(keys) => {
                  const selectedKey = keys[0];
                  if (typeof selectedKey === 'string' && selectedKey.startsWith('case:')) {
                    const caseKey = selectedKey.replace(/^case:/, '');
                    setSelectedCaseKey(caseKey);
                    if (viewVersionKey) {
                      void refreshCaseDetail(viewVersionKey, caseKey);
                    }
                  }
                }}
              />
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card
            title="用例详情"
            loading={loading}
            extra={
              detail?.caseInfo && canEditTree ? (
                <Space>
                  <Button size="small" onClick={openEditCaseModal}>
                    编辑用例
                  </Button>
                  <Button
                    size="small"
                    danger
                    onClick={() => {
                      Modal.confirm({
                        title: '确认删除用例',
                        content: `删除后该用例将从用例树中隐藏：${detail.caseInfo.caseKey}`,
                        okText: '删除',
                        cancelText: '取消',
                        onOk: async () => {
                          await deleteCase();
                        },
                      });
                    }}
                  >
                    删除用例
                  </Button>
                </Space>
              ) : null
            }
          >
            {!detail ? (
              <Alert type="info" showIcon message="请选择左侧用例" />
            ) : (
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label="用例 ID">{detail.caseInfo.caseKey}</Descriptions.Item>
                <Descriptions.Item label="名称">{detail.caseInfo.title}</Descriptions.Item>
                <Descriptions.Item label="模块">{detail.caseInfo.module}</Descriptions.Item>
                <Descriptions.Item label="测试步骤">{detail.caseInfo.steps}</Descriptions.Item>
                <Descriptions.Item label="预期结果">{detail.caseInfo.expected}</Descriptions.Item>
                <Descriptions.Item label="标签">
                  <Space wrap>
                    {(detail.caseInfo.tags ?? []).map((tag) => (
                      <Tag key={tag}>{tag}</Tag>
                    ))}
                  </Space>
                </Descriptions.Item>
              </Descriptions>
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
          </Space>
        )}
      </Modal>

      <Modal
        title="新增目录"
        open={nodeModalOpen}
        onCancel={() => setNodeModalOpen(false)}
        onOk={createDirectory}
        confirmLoading={nodeSubmitting}
        okText="创建"
      >
        <Form layout="vertical" form={nodeForm}>
          <Form.Item label="父节点">
            <Input value={actionNode?.fullPath ?? '-'} disabled />
          </Form.Item>
          <Form.Item label="目录名" name="name" rules={[{ required: true, message: '请输入目录名' }]}>
            <Input maxLength={128} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="新增用例"
        open={caseModalOpen}
        onCancel={() => setCaseModalOpen(false)}
        onOk={createCase}
        confirmLoading={caseSubmitting}
        okText="创建"
        width={760}
      >
        <Form layout="vertical" form={caseForm}>
          <Form.Item label="父节点">
            <Input value={actionNode?.fullPath ?? '-'} disabled />
          </Form.Item>
          <Form.Item label="用例编号" name="caseKey" rules={[{ required: true, message: '请输入用例编号' }]}>
            <Input maxLength={32} />
          </Form.Item>
          <Form.Item label="标题" name="title" rules={[{ required: true, message: '请输入标题' }]}>
            <Input maxLength={256} />
          </Form.Item>
          <Form.Item label="测试步骤" name="steps" rules={[{ required: true, message: '请输入测试步骤' }]}>
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item label="预期结果" name="expected" rules={[{ required: true, message: '请输入预期结果' }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item label="标签（逗号分隔）" name="tags">
            <Input placeholder="例如：jsonrpc,p0,transfer" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="编辑用例"
        open={editModalOpen}
        onCancel={() => setEditModalOpen(false)}
        onOk={updateCase}
        confirmLoading={editSubmitting}
        okText="保存"
        width={760}
      >
        <Form layout="vertical" form={editForm}>
          <Form.Item label="挂载节点" name="parentNodeId">
            <Select showSearch optionFilterProp="label" options={nodeOptions} placeholder="保持原节点可不修改" />
          </Form.Item>
          <Form.Item label="标题" name="title" rules={[{ required: true, message: '请输入标题' }]}>
            <Input maxLength={256} />
          </Form.Item>
          <Form.Item label="测试步骤" name="steps" rules={[{ required: true, message: '请输入测试步骤' }]}>
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item label="预期结果" name="expected" rules={[{ required: true, message: '请输入预期结果' }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item label="标签（逗号分隔）" name="tags">
            <Input placeholder="例如：jsonrpc,p0,transfer" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
