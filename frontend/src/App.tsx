import {
  BellOutlined,
  BookOutlined,
  CheckCircleFilled,
  CloudUploadOutlined,
  CopyOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  LogoutOutlined,
  FileExcelOutlined,
  FilePdfOutlined,
  FilePptOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  HomeOutlined,
  InfoCircleOutlined,
  MessageOutlined,
  MoreOutlined,
  NodeIndexOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  SendOutlined,
  SettingOutlined,
  TeamOutlined,
  UserOutlined
} from '@ant-design/icons';
import {
  Alert,
  App as AntApp,
  Avatar,
  Badge,
  Button,
  Dropdown,
  Empty,
  Input,
  Modal,
  Progress,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
  Upload
} from 'antd';
import type { MenuProps, UploadProps } from 'antd';
import dayjs from 'dayjs';
import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  askKnowledgeBase,
  createKnowledgeBase,
  deleteKnowledgeBase,
  getEvalSummary,
  getModelConfig,
  getCurrentUser,
  listDocumentChunks,
  listDocuments,
  listKnowledgeBases,
  listQALogs,
  login,
  logout as clearLogin,
  rebuildDocument,
  streamAskKnowledgeBase,
  switchRole,
  updateModelConfig,
  uploadDocument
} from './api/client';
import type { AskResponse, ChatMessage, ChunkItem, CurrentUser, DocumentItem, EvalSummary, KnowledgeBase, ModelConfig, QALog, RetrievalResult } from './types';

const { Text, Title, Paragraph } = Typography;

const sampleQuestions = ['报销制度', '转正流程', '报销需要哪些材料？'];

const roleOptions = [
  { value: 'admin', label: '管理员', scope: '全部知识库、模型设置、操作日志' },
  { value: 'manager', label: '部门负责人', scope: '部门制度、报销、转正、审批流程' },
  { value: 'hr', label: 'HR', scope: '公开制度、考勤、报销、通用流程' },
  { value: 'employee', label: '普通员工', scope: '公开制度、考勤、报销、通用流程' }
];

type SectionKey = 'home' | 'knowledge' | 'qa' | 'ingest' | 'permissions' | 'settings' | 'eval' | 'logs';

type AnswerDetail = {
  title: string;
  question?: string;
  answer: string;
  citations: AskResponse['citations'];
  retrievalResults: RetrievalResult[];
  meta?: string;
};

const navItems: Array<{ key: SectionKey; label: string; icon: ReactNode }> = [
  { key: 'home', label: '首页', icon: <HomeOutlined /> },
  { key: 'knowledge', label: '知识库', icon: <BookOutlined /> },
  { key: 'qa', label: '智能问答', icon: <MessageOutlined /> },
  { key: 'ingest', label: '数据接入', icon: <DatabaseOutlined /> },
  { key: 'permissions', label: '权限管理', icon: <TeamOutlined /> },
  { key: 'settings', label: '系统设置', icon: <SettingOutlined /> },
  { key: 'eval', label: 'RAG 评测', icon: <NodeIndexOutlined /> },
  { key: 'logs', label: '操作日志', icon: <FileTextOutlined /> }
];

function getHttpStatus(error: unknown) {
  if (typeof error !== 'object' || error === null || !('response' in error)) return undefined;
  return (error as { response?: { status?: number } }).response?.status;
}

function getUploadErrorMessage(error: unknown) {
  if (getHttpStatus(error) === 413) {
    return '文件超过上传限制，请压缩文件或联系管理员调整上传大小';
  }
  return '上传失败，请稍后重试';
}

function App() {
  const { message, modal } = AntApp.useApp();
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKbId, setSelectedKbId] = useState<string>();
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [logs, setLogs] = useState<QALog[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [latestAnswer, setLatestAnswer] = useState<AskResponse>();
  const [question, setQuestion] = useState('');
  const [topK, setTopK] = useState(8);
  const [loading, setLoading] = useState(false);
  const [booting, setBooting] = useState(true);
  const [kbModalOpen, setKbModalOpen] = useState(false);
  const [newKbName, setNewKbName] = useState('');
  const [newKbDesc, setNewKbDesc] = useState('');
  const [newKbCategory, setNewKbCategory] = useState<'policy' | 'business' | 'general'>('policy');
  const [systemError, setSystemError] = useState('');
  const [activeSection, setActiveSection] = useState<SectionKey>('qa');
  const [currentUser, setCurrentUser] = useState<CurrentUser>();
  const [modelConfig, setModelConfig] = useState<ModelConfig>();
  const [evalSummary, setEvalSummary] = useState<EvalSummary>();
  const [creatingKb, setCreatingKb] = useState(false);
  const [rebuildingDocId, setRebuildingDocId] = useState<string>();
  const [answerDetail, setAnswerDetail] = useState<AnswerDetail>();
  const [documentDetail, setDocumentDetail] = useState<{ doc: DocumentItem; chunks: ChunkItem[] }>();
  const [documentDetailLoading, setDocumentDetailLoading] = useState(false);

  const selectedKb = useMemo(() => knowledgeBases.find((item) => item.id === selectedKbId), [knowledgeBases, selectedKbId]);
  const completedDocs = documents.filter((doc) => doc.status === 'completed').length;
  const failedDocs = documents.filter((doc) => doc.status === 'failed').length;
  const totalChunks = documents.reduce((sum, doc) => sum + doc.chunk_count, 0);
  const totalChars = documents.reduce((sum, doc) => sum + doc.char_count, 0);
  const selectedKbLogs = selectedKbId ? logs.filter((log) => log.knowledge_base_id === selectedKbId) : logs;
  const latestQuestion = [...messages].reverse().find((item) => item.role === 'user')?.content;
  const allDocCount = knowledgeBases.reduce((sum, kb) => sum + kb.document_count, 0);
  const pendingDocumentCount = documents.filter((doc) => doc.status === 'pending' || doc.status === 'processing' || doc.status === 'failed').length;
  const canManageKnowledge = currentUser ? currentUser.role === 'admin' || currentUser.role === 'manager' : false;
  const canWriteDocuments = currentUser ? currentUser.role !== 'employee' : false;

  async function refreshAll(nextKbId?: string) {
    const kbs = await listKnowledgeBases();
    setKnowledgeBases(kbs);
    const target = kbs.find((kb) => kb.id === (nextKbId || selectedKbId))?.id || kbs[0]?.id;
    setSelectedKbId(target);
    setDocuments(target ? await listDocuments(target) : []);
    setLogs(await listQALogs());
    setModelConfig(await getModelConfig());
    setEvalSummary(await getEvalSummary());
    setSystemError('');
  }

  async function handleLogin(username: string, password: string) {
    try {
      const response = await login(username, password);
      setCurrentUser(response.user);
      await refreshAll();
      message.success(`欢迎回来，${response.user.name}`);
    } catch {
      message.error('账号或密码错误');
      throw new Error('login failed');
    }
  }

  function handleLogout() {
    clearLogin();
    setCurrentUser(undefined);
    setKnowledgeBases([]);
    setSelectedKbId(undefined);
    setDocuments([]);
    setLogs([]);
    setMessages([]);
    setLatestAnswer(undefined);
    setModelConfig(undefined);
    setEvalSummary(undefined);
    setActiveSection('qa');
    message.success('已退出登录');
  }

  useEffect(() => {
    const token = localStorage.getItem('rag_access_token');
    if (!token) {
      setBooting(false);
      return;
    }
    getCurrentUser()
      .then((user) => {
        setCurrentUser(user);
        return refreshAll();
      })
      .catch(() => {
        clearLogin();
        setCurrentUser(undefined);
        message.warning('登录已过期，请重新登录');
      })
      .finally(() => setBooting(false));
  }, []);

  useEffect(() => {
    if (!selectedKbId) return;
    listDocuments(selectedKbId).then(setDocuments).catch(() => message.error('文档列表加载失败'));
  }, [selectedKbId]);

  async function handleCreateKb() {
    if (!newKbName.trim()) {
      message.warning('请输入知识库名称');
      return;
    }
    setCreatingKb(true);
    try {
      const kb = await createKnowledgeBase(newKbName.trim(), newKbDesc.trim(), newKbCategory);
      setKbModalOpen(false);
      setNewKbName('');
      setNewKbDesc('');
      setNewKbCategory('policy');
      await refreshAll(kb.id);
      message.success('知识库已创建');
    } catch {
      message.error('知识库创建失败，请稍后重试');
    } finally {
      setCreatingKb(false);
    }
  }

  function handleDeleteKb(id: string) {
    modal.confirm({
      title: '删除知识库',
      content: '该操作会同时删除知识库内文档、切片和问答日志，确认继续？',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteKnowledgeBase(id);
          setLatestAnswer(undefined);
          setMessages([]);
          await refreshAll();
          message.success('知识库已删除');
        } catch {
          message.error('知识库删除失败，请确认权限或稍后重试');
        }
      }
    });
  }

  async function handleRebuildDocument(doc: DocumentItem) {
    setRebuildingDocId(doc.id);
    try {
      await rebuildDocument(doc.id);
      if (selectedKbId) setDocuments(await listDocuments(selectedKbId));
      message.success('索引已重建');
    } catch {
      message.error('索引重建失败，请确认权限或查看后端日志');
    } finally {
      setRebuildingDocId(undefined);
    }
  }

  async function openDocumentDetail(doc: DocumentItem) {
    setDocumentDetail({ doc, chunks: [] });
    setDocumentDetailLoading(true);
    try {
      const chunks = await listDocumentChunks(doc.id);
      setDocumentDetail({ doc, chunks });
    } catch {
      message.error('文档切片加载失败');
      setDocumentDetail(undefined);
    } finally {
      setDocumentDetailLoading(false);
    }
  }

  async function handleAsk(nextQuestion?: string) {
    const current = (nextQuestion ?? question).trim();
    if (!selectedKbId) {
      message.warning('请先创建或选择知识库');
      return;
    }
    if (!current) return;

    setQuestion('');
    setMessages((items) => [...items, { role: 'user', content: current }]);
    setLatestAnswer({
      answer: '',
      citations: [],
      retrieval_results: [],
      latency_ms: 0,
      model_name: '',
      token_estimate: 0,
      hit_knowledge_base: false,
      prompt_version: ''
    });
    setLoading(true);
    try {
      let streamed = '';
      await streamAskKnowledgeBase(selectedKbId, current, topK, {
        onMetadata: (metadata) => setLatestAnswer((prev) => ({ ...(prev || ({} as AskResponse)), ...metadata, answer: streamed } as AskResponse)),
        onToken: (delta) => {
          streamed += delta;
          setLatestAnswer((prev) => ({ ...(prev || ({} as AskResponse)), answer: streamed } as AskResponse));
        },
        onDone: (answer) => {
          streamed = answer.answer;
          setLatestAnswer(answer);
          setMessages((items) => [...items, { role: 'assistant', content: answer.answer }]);
        }
      });
      setLogs(await listQALogs());
      setEvalSummary(await getEvalSummary());
    } catch {
      try {
        const answer = await askKnowledgeBase(selectedKbId, current, topK);
        setLatestAnswer(answer);
        setMessages((items) => [...items, { role: 'assistant', content: answer.answer }]);
        setLogs(await listQALogs());
      } catch {
        message.error('问答请求失败，请查看后端日志');
      }
    } finally {
      setLoading(false);
    }
  }

  const uploadProps: UploadProps = {
    showUploadList: false,
    beforeUpload: async (file) => {
      if (!selectedKbId) {
        message.warning('请先选择知识库');
        return Upload.LIST_IGNORE;
      }
      if (!canWriteDocuments) {
        message.warning('当前角色无文档写入权限');
        return Upload.LIST_IGNORE;
      }
      const hide = message.loading('正在解析、切分并写入向量索引...', 0);
      try {
        const doc = await uploadDocument(selectedKbId, file);
        await refreshAll(selectedKbId);
        if (doc.status === 'failed') {
          message.error(doc.error_message || '文档索引失败');
        } else {
          message.success('文档已完成索引');
        }
      } catch (error) {
        message.error(getUploadErrorMessage(error));
      } finally {
        hide();
      }
      return Upload.LIST_IGNORE;
    }
  };

  if (booting) {
    return (
      <div className="boot">
        <Spin tip="正在连接 RAG 服务..." />
      </div>
    );
  }

  if (!currentUser) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <div className="console-shell">
      <TopBar
        currentUser={currentUser}
        notificationCount={pendingDocumentCount}
        setActiveSection={setActiveSection}
        onSearch={(value) => {
          setQuestion(value);
          setActiveSection('qa');
        }}
        onHelp={() => message.info('支持知识库管理、文档接入、RAG 问答、引用溯源、日志审计和参数配置。')}
        onLogout={handleLogout}
      />

      <aside className="left-rail">
        <div className="brand-mobile">
          <Brand />
        </div>
        <nav className="main-nav">
          {navItems.map((item) => (
            <NavItem
              key={item.key}
              icon={item.icon}
              label={item.label}
              active={activeSection === item.key}
              onClick={() => setActiveSection(item.key)}
            />
          ))}
        </nav>

        <section className="quick-card">
          <h3>快捷入口</h3>
          <Upload {...uploadProps} accept=".pdf,.docx,.txt,.md,.markdown">
            <QuickAction icon={<CloudUploadOutlined />} title="上传文档 / 构建知识库" desc="支持多种格式文档" disabled={!selectedKbId || !canWriteDocuments} />
          </Upload>
          <button className="quick-action" onClick={() => setActiveSection('knowledge')}>
            <span className="quick-icon"><BookOutlined /></span>
            <span><strong>管理知识库</strong><em>查看与维护知识库</em></span>
          </button>
          <button className="quick-action" onClick={() => setActiveSection('settings')}>
            <span className="quick-icon"><NodeIndexOutlined /></span>
            <span><strong>配置模型与参数</strong><em>管理 RAG 与模型设置</em></span>
          </button>
        </section>
      </aside>

      <main className="work-area">
        {activeSection === 'home' && (
          <HomePage
            knowledgeBases={knowledgeBases}
            documents={documents}
            logs={logs}
            totalChunks={totalChunks}
            allDocCount={allDocCount}
            setActiveSection={setActiveSection}
          />
        )}

        {activeSection === 'knowledge' && (
          <KnowledgePage
            currentUser={currentUser}
            knowledgeBases={knowledgeBases}
            selectedKbId={selectedKbId}
            setSelectedKbId={setSelectedKbId}
            documents={documents}
            openCreate={() => canManageKnowledge && setKbModalOpen(true)}
            deleteKb={handleDeleteKb}
          />
        )}

        {activeSection === 'ingest' && (
          <IngestPage
            selectedKb={selectedKb}
            documents={documents}
            uploadProps={uploadProps}
            canWriteDocuments={canWriteDocuments}
            rebuildingDocId={rebuildingDocId}
            onRebuild={handleRebuildDocument}
            onOpenDocument={openDocumentDetail}
          />
        )}

        {activeSection === 'permissions' && (
          <PermissionsPage
            currentUser={currentUser}
            setCurrentUser={setCurrentUser}
            onRoleChange={async (role) => {
              const response = await switchRole(role);
              setCurrentUser(response.user);
              await refreshAll();
              message.success(`当前账号角色已切换为：${response.user.role_label}`);
              return response.user;
            }}
          />
        )}

        {activeSection === 'settings' && (
          <SettingsPage
            currentUser={currentUser}
            topK={topK}
            setTopK={setTopK}
            modelConfig={modelConfig}
            onSave={async (payload) => {
              const next = await updateModelConfig(payload);
              setModelConfig(next);
              message.success('模型配置已保存');
            }}
          />
        )}

        {activeSection === 'eval' && <EvalPage summary={evalSummary} logs={logs} />}

        {activeSection === 'logs' && <LogsPage logs={logs} knowledgeBases={knowledgeBases} onOpenDetail={setAnswerDetail} />}

        {activeSection === 'qa' && (
        <section className="chat-card">
          <div className="card-title-row">
            <div className="title-inline">
              <h2>智能问答</h2>
              <Tag className="rag-tag">RAG</Tag>
              <span>基于企业知识库的智能检索增强生成</span>
            </div>
            <div className="kb-tools">
              <Select
                className="kb-select"
                value={selectedKbId}
                placeholder="选择知识库"
                onChange={(value) => {
                  setSelectedKbId(value);
                  setLatestAnswer(undefined);
                  setMessages([]);
                }}
                options={knowledgeBases.map((kb) => ({ value: kb.id, label: kb.name }))}
                popupMatchSelectWidth={280}
              />
              <Tooltip title="新建知识库">
                <Button icon={<PlusOutlined />} disabled={!canManageKnowledge} onClick={() => setKbModalOpen(true)} />
              </Tooltip>
              <Tooltip title="删除当前知识库">
                <Button icon={<DeleteOutlined />} danger disabled={!selectedKbId || !canManageKnowledge} onClick={() => selectedKbId && handleDeleteKb(selectedKbId)} />
              </Tooltip>
            </div>
          </div>

          {systemError && <Alert className="system-alert" type="error" showIcon message={systemError} />}

          <div className="conversation-panel">
            {messages.length === 0 ? (
              <EmptyState onAsk={handleAsk} disabled={!selectedKbId || loading} />
            ) : (
              <>
                {latestQuestion && (
                  <div className="dialog-row user-row">
                    <Avatar className="avatar-user" icon={<UserOutlined />} />
                    <div className="dialog-content user-content">
                      <div className="dialog-head">
                        <strong>我</strong>
                        <span>今天 {dayjs().format('HH:mm')}</span>
                      </div>
                      <Paragraph>{latestQuestion}</Paragraph>
                    </div>
                  </div>
                )}

                <div className="dialog-row assistant-row">
                  <Avatar className="avatar-ai" icon={<RobotOutlined />} />
                  <div className="dialog-content assistant-content">
                    <div className="dialog-head">
                      <strong>AI 助手</strong>
                    </div>
                    {loading && latestAnswer?.answer ? (
                      <>
                        <Paragraph className="answer-text streaming-answer">{latestAnswer.answer}</Paragraph>
                        <div className="loading-answer">
                          <Spin size="small" />
                          <span>SSE 流式输出中...</span>
                        </div>
                      </>
                    ) : loading ? (
                      <div className="loading-answer">
                        <Spin size="small" />
                        <span>正在检索知识库、重排片段并生成答案...</span>
                      </div>
                    ) : latestAnswer ? (
                      <>
                        <Paragraph className="answer-text">{latestAnswer.answer}</Paragraph>
                        <div className="answer-actions">
                          <button onClick={() => {
                            navigator.clipboard?.writeText(latestAnswer.answer);
                            message.success('答案已复制');
                          }}><CopyOutlined />复制</button>
                          <button onClick={() => message.success('感谢反馈，已记录本次评价')}><CheckCircleFilled />有帮助</button>
                          <button onClick={() => message.info('已收到反馈，建议补充文档或调整问题后重试')}><InfoCircleOutlined />没帮助</button>
                          <span><CheckCircleFilled />由企业知识库生成</span>
                        </div>
                      </>
                    ) : null}
                  </div>
                </div>
              </>
            )}
          </div>

          <EvidenceGrid
            latestAnswer={latestAnswer}
            latestQuestion={latestQuestion}
            documents={documents}
            setActiveSection={setActiveSection}
            onOpenDetail={setAnswerDetail}
          />

          <div className="ask-composer">
            <Input.TextArea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onPressEnter={(event) => {
                if (!event.shiftKey) {
                  event.preventDefault();
                  handleAsk();
                }
              }}
              autoSize={{ minRows: 1, maxRows: 4 }}
              placeholder="请输入您的问题，Enter 发送，Shift + Enter 换行"
            />
            <div className="composer-tools">
              <Select
                size="small"
                value={topK}
                onChange={setTopK}
                options={[4, 6, 8, 10, 12].map((value) => ({ value, label: `深度思考（召回 ${value}）` }))}
              />
              <Button className="send-button" type="primary" icon={<SendOutlined />} loading={loading} onClick={() => handleAsk()} />
            </div>
          </div>
        </section>
        )}
      </main>

      <aside className="right-rail">
        <ModelPanel currentUser={currentUser} topK={topK} setTopK={setTopK} modelConfig={modelConfig} openSettings={() => setActiveSection('settings')} />
        <HealthPanel documents={documents} totalChunks={totalChunks} totalChars={totalChars} failedDocs={failedDocs} openIngest={() => setActiveSection('ingest')} />
        <TrendPanel logs={selectedKbLogs} latestAnswer={latestAnswer} />
        <RecentDocs
          documents={documents}
          canWriteDocuments={canWriteDocuments}
          rebuildingDocId={rebuildingDocId}
          onRebuild={handleRebuildDocument}
          openIngest={() => setActiveSection('ingest')}
        />
      </aside>

      <Modal
        title="新建知识库"
        open={kbModalOpen}
        onOk={handleCreateKb}
        confirmLoading={creatingKb}
        onCancel={() => {
          setKbModalOpen(false);
          setNewKbName('');
          setNewKbDesc('');
          setNewKbCategory('policy');
        }}
        okText="创建"
        cancelText="取消"
      >
        <Space direction="vertical" className="full-width">
          <Input placeholder="知识库名称，例如：企业制度知识库" value={newKbName} onChange={(event) => setNewKbName(event.target.value)} />
          <Select
            value={newKbCategory}
            onChange={setNewKbCategory}
            options={[
              { value: 'policy', label: '制度类' },
              { value: 'business', label: '业务类' },
              { value: 'general', label: '通用类' }
            ]}
          />
          <Input.TextArea placeholder="描述，可选" value={newKbDesc} onChange={(event) => setNewKbDesc(event.target.value)} rows={3} />
        </Space>
      </Modal>
      <AnswerDetailModal detail={answerDetail} onClose={() => setAnswerDetail(undefined)} />
      <DocumentDetailModal
        detail={documentDetail}
        loading={documentDetailLoading}
        onClose={() => setDocumentDetail(undefined)}
      />
    </div>
  );
}

function LoginPage({ onLogin }: { onLogin: (username: string, password: string) => Promise<void> }) {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('admin123');
  const [loading, setLoading] = useState(false);

  async function submit() {
    setLoading(true);
    try {
      await onLogin(username, password);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-card">
        <Brand />
        <div className="login-copy">
          <h2>登录企业知识库工作台</h2>
          <p>使用演示账号进入 RAG 问答、知识库管理、权限和日志审计。</p>
        </div>
        <label className="form-label">账号</label>
        <Input value={username} onChange={(event) => setUsername(event.target.value)} onPressEnter={submit} />
        <label className="form-label">密码</label>
        <Input.Password value={password} onChange={(event) => setPassword(event.target.value)} onPressEnter={submit} />
        <Button type="primary" size="large" block loading={loading} onClick={submit}>登录</Button>
        <div className="demo-accounts">
          <strong>演示账号</strong>
          <button onClick={() => { setUsername('admin'); setPassword('admin123'); }}>管理员 admin/admin123</button>
          <button onClick={() => { setUsername('manager'); setPassword('manager123'); }}>部门负责人 manager/manager123</button>
          <button onClick={() => { setUsername('hr'); setPassword('hr123'); }}>HR hr/hr123</button>
          <button onClick={() => { setUsername('employee'); setPassword('employee123'); }}>普通员工 employee/employee123</button>
        </div>
      </section>
    </main>
  );
}

function HomePage({
  knowledgeBases,
  documents,
  logs,
  totalChunks,
  allDocCount,
  setActiveSection
}: {
  knowledgeBases: KnowledgeBase[];
  documents: DocumentItem[];
  logs: QALog[];
  totalChunks: number;
  allDocCount: number;
  setActiveSection: (section: SectionKey) => void;
}) {
  const hitRate = logs.length ? Math.round((logs.filter((item) => item.hit_knowledge_base).length / logs.length) * 100) : 0;
  return (
    <section className="page-card">
      <div className="page-head">
        <div>
          <Title level={3}>首页</Title>
          <Text type="secondary">企业知识库 RAG 系统运行概览</Text>
        </div>
        <Space>
          <Button icon={<CloudUploadOutlined />} onClick={() => setActiveSection('ingest')}>上传文档</Button>
          <Button type="primary" icon={<MessageOutlined />} onClick={() => setActiveSection('qa')}>开始问答</Button>
        </Space>
      </div>

      <div className="overview-grid">
        <OverviewCard title="知识库" value={knowledgeBases.length} note={`${allDocCount} 个文档`} icon={<BookOutlined />} />
        <OverviewCard title="当前文档" value={documents.length} note={`${totalChunks} 个知识切片`} icon={<FileTextOutlined />} />
        <OverviewCard title="问答记录" value={logs.length} note={`${hitRate}% 命中率`} icon={<MessageOutlined />} />
        <OverviewCard title="系统状态" value="正常" note="Mock/OpenAI 兼容模式" icon={<SafetyCertificateOutlined />} />
      </div>

      <div className="page-grid two">
        <section className="management-card">
          <div className="mini-title"><BookOutlined />最近知识库</div>
          {knowledgeBases.length ? knowledgeBases.slice(0, 5).map((kb) => (
            <button className="list-row-button" key={kb.id} onClick={() => setActiveSection('knowledge')}>
              <span><strong>{kb.name}</strong><em>{kb.description || '暂无描述'}</em></span>
              <Tag>{kb.category_label} · {kb.document_count} 文档</Tag>
            </button>
          )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无知识库" />}
        </section>

        <section className="management-card">
          <div className="mini-title"><HistoryIcon />最近问答</div>
          {logs.length ? logs.slice(0, 5).map((log) => (
            <div className="log-row" key={log.id}>
              <strong>{log.question}</strong>
              <span>{dayjs(log.created_at).format('MM-DD HH:mm')} · {log.hit_knowledge_base ? '命中知识库' : '已拒答'}</span>
            </div>
          )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无问答日志" />}
        </section>
      </div>
    </section>
  );
}

function KnowledgePage({
  currentUser,
  knowledgeBases,
  selectedKbId,
  setSelectedKbId,
  documents,
  openCreate,
  deleteKb
}: {
  currentUser: CurrentUser;
  knowledgeBases: KnowledgeBase[];
  selectedKbId?: string;
  setSelectedKbId: (id: string) => void;
  documents: DocumentItem[];
  openCreate: () => void;
  deleteKb: (id: string) => void;
}) {
  const canDelete = currentUser.role === 'admin' || currentUser.role === 'manager';
  return (
    <section className="page-card">
      <div className="page-head">
        <div>
          <Title level={3}>知识库管理</Title>
          <Text type="secondary">创建、选择、删除知识库，并查看当前知识库文档</Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} disabled={!canDelete} onClick={openCreate}>新建知识库</Button>
      </div>

      <div className="kb-management-grid">
        <section className="management-card">
          <div className="mini-title"><BookOutlined />知识库列表</div>
          {knowledgeBases.length ? knowledgeBases.map((kb) => (
            <div className={`kb-manage-item ${kb.id === selectedKbId ? 'active' : ''}`} key={kb.id}>
              <button onClick={() => setSelectedKbId(kb.id)}>
                <strong>{kb.name}</strong>
                <span>{kb.description || '暂无描述'} · {kb.category_label} · {kb.document_count} 个文档</span>
              </button>
              <Tooltip title={canDelete ? '删除知识库' : '当前角色无删除权限'}>
                <Button danger type="text" icon={<DeleteOutlined />} disabled={!canDelete} onClick={() => deleteKb(kb.id)} />
              </Tooltip>
            </div>
          )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无知识库" />}
        </section>

        <section className="management-card">
          <div className="mini-title"><FileTextOutlined />当前知识库文档</div>
          {documents.length ? documents.map((doc) => (
            <div className="doc-manage-row" key={doc.id}>
              {fileIcon(doc.filename)}
              <span><strong>{doc.filename}</strong><em>{doc.chunk_count} 切片 · {formatNumber(doc.char_count)} 字符</em></span>
              <Tag color={statusColor(doc.status)}>{statusText(doc.status)}</Tag>
            </div>
          )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无文档" />}
        </section>
      </div>
    </section>
  );
}

function IngestPage({
  selectedKb,
  documents,
  uploadProps,
  canWriteDocuments,
  rebuildingDocId,
  onRebuild,
  onOpenDocument
}: {
  selectedKb?: KnowledgeBase;
  documents: DocumentItem[];
  uploadProps: UploadProps;
  canWriteDocuments: boolean;
  rebuildingDocId?: string;
  onRebuild: (doc: DocumentItem) => void;
  onOpenDocument: (doc: DocumentItem) => void;
}) {
  return (
    <section className="page-card">
      <div className="page-head">
        <div>
          <Title level={3}>数据接入</Title>
          <Text type="secondary">{selectedKb ? `当前知识库：${selectedKb.name}` : '请先选择或创建知识库'}</Text>
        </div>
        <Upload {...uploadProps} accept=".pdf,.docx,.txt,.md,.markdown">
          <Button type="primary" icon={<CloudUploadOutlined />} disabled={!selectedKb || !canWriteDocuments}>上传文档</Button>
        </Upload>
      </div>

      <div className="upload-drop">
        <CloudUploadOutlined />
        <h3>上传 PDF、DOCX、TXT、Markdown 文档</h3>
        <p>系统会自动解析正文、切分 chunk、生成 embedding，并写入 pgvector。</p>
        <Upload {...uploadProps} accept=".pdf,.docx,.txt,.md,.markdown">
          <Button icon={<CloudUploadOutlined />} disabled={!selectedKb || !canWriteDocuments}>选择文件</Button>
        </Upload>
      </div>

      <section className="management-card">
        <div className="mini-title"><DatabaseOutlined />索引任务</div>
        {documents.length ? documents.map((doc) => (
          <div className="ingest-row" key={doc.id}>
            {fileIcon(doc.filename)}
            <span><strong>{doc.filename}</strong><em>{dayjs(doc.created_at).format('YYYY-MM-DD HH:mm')} · {doc.chunk_count} 切片</em></span>
            <Tag color={statusColor(doc.status)}>{statusText(doc.status)}</Tag>
            <Button icon={<FileSearchOutlined />} onClick={() => onOpenDocument(doc)}>查看切片</Button>
            <Button
              icon={<ReloadOutlined />}
              disabled={!canWriteDocuments}
              loading={rebuildingDocId === doc.id}
              onClick={() => onRebuild(doc)}
            >
              重建索引
            </Button>
          </div>
        )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无接入任务" />}
      </section>
    </section>
  );
}

function PermissionsPage({
  currentUser,
  setCurrentUser,
  onRoleChange
}: {
  currentUser: CurrentUser;
  setCurrentUser: (user: CurrentUser) => void;
  onRoleChange: (role: string) => Promise<CurrentUser>;
}) {
  const { message } = AntApp.useApp();
  const [scope, setScope] = useState(currentUser.access_scope);
  const [switchingRole, setSwitchingRole] = useState(false);
  const canSwitchRole = currentUser.username === 'admin';

  async function updateRole(role: string) {
    setSwitchingRole(true);
    try {
      const nextUser = await onRoleChange(role);
      setScope(nextUser.access_scope);
    } catch {
      message.error('角色切换失败，请确认当前账号权限');
    } finally {
      setSwitchingRole(false);
    }
  }

  return (
    <section className="page-card">
      <div className="page-head">
        <div>
          <Title level={3}>权限管理</Title>
          <Text type="secondary">当前版本提供前端权限策略配置演示，后续可接入真实账号体系</Text>
        </div>
        <Tag color="green">演示配置</Tag>
      </div>
      <div className="page-grid two">
        <section className="management-card">
          <div className="mini-title"><TeamOutlined />角色策略</div>
          <label className="form-label">角色</label>
          <Select
            value={currentUser.role}
            loading={switchingRole}
            disabled={!canSwitchRole}
            onChange={updateRole}
            options={roleOptions.map(({ value, label }) => ({ value, label }))}
          />
          <label className="form-label">可访问范围</label>
          <Input.TextArea
            value={scope}
            onChange={(event) => {
              setScope(event.target.value);
              setCurrentUser({ ...currentUser, access_scope: event.target.value });
            }}
            rows={4}
          />
          <Alert type="info" showIcon message={`${currentUser.role_label} 可访问：${scope}`} />
          {!canSwitchRole && <Alert type="warning" showIcon message="只有 admin 演示账号可以切换角色，普通账号不能提权。" />}
        </section>
        <section className="management-card">
          <div className="mini-title"><SafetyCertificateOutlined />安全能力</div>
          <div className="feature-list">
            <span><CheckCircleFilled />知识库级别访问控制</span>
            <span><CheckCircleFilled />问答日志审计</span>
            <span><CheckCircleFilled />引用来源追踪</span>
            <span><CheckCircleFilled />拒答策略保护</span>
          </div>
        </section>
      </div>
    </section>
  );
}

function SettingsPage({
  currentUser,
  topK,
  setTopK,
  modelConfig,
  onSave
}: {
  currentUser: CurrentUser;
  topK: number;
  setTopK: (value: number) => void;
  modelConfig?: ModelConfig;
  onSave: (payload: Partial<ModelConfig>) => Promise<void>;
}) {
  const { message } = AntApp.useApp();
  const [chatModel, setChatModel] = useState(modelConfig?.chat_model || 'gpt-4o-mini');
  const [llmMode, setLlmMode] = useState(modelConfig?.llm_mode || 'mock');
  const [saving, setSaving] = useState(false);
  const canConfigure = currentUser.role === 'admin';

  useEffect(() => {
    if (!modelConfig) return;
    setChatModel(modelConfig.chat_model);
    setLlmMode(modelConfig.llm_mode);
    setTopK(modelConfig.retrieval_top_k);
  }, [modelConfig]);

  async function handleSave() {
    setSaving(true);
    try {
      await onSave({ chat_model: chatModel, llm_mode: llmMode, retrieval_top_k: topK });
    } catch {
      message.error('模型配置保存失败，请稍后重试');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="page-card">
      <div className="page-head">
        <div>
          <Title level={3}>系统设置</Title>
          <Text type="secondary">配置检索、模型和回答策略</Text>
        </div>
        <Tag color={canConfigure ? 'green' : 'orange'}>{canConfigure ? '管理员可配置' : '只读模式'}</Tag>
      </div>
      <div className="page-grid two">
        <section className="management-card">
          <div className="mini-title"><SettingOutlined />模型与检索</div>
          <label className="form-label">当前模型</label>
          <Input value={chatModel} disabled={!canConfigure} onChange={(event) => setChatModel(event.target.value)} />
          <label className="form-label">模型模式</label>
          <Select
            value={llmMode}
            disabled={!canConfigure}
            onChange={setLlmMode}
            options={[
              { value: 'mock', label: 'Mock 演示模式' },
              { value: 'openai', label: 'OpenAI-compatible' }
            ]}
          />
          <label className="form-label">召回数量 Top K</label>
          <Select value={topK} disabled={!canConfigure} onChange={setTopK} options={[4, 6, 8, 10, 12, 20].map((value) => ({ value, label: `Top ${value}` }))} />
          <label className="form-label">检索策略</label>
          <Select value="混合检索（向量 + 关键词）" options={[{ value: '混合检索（向量 + 关键词）', label: '混合检索（向量 + 关键词）' }]} />
          <Button
            type="primary"
            disabled={!canConfigure}
            loading={saving}
            onClick={handleSave}
          >
            保存配置
          </Button>
          {!canConfigure && <Alert type="warning" showIcon message="只有管理员可以修改模型配置，当前角色只能查看。" />}
        </section>
        <section className="management-card">
          <div className="mini-title"><RobotOutlined />Prompt 策略</div>
          <div className="feature-list">
            <span><CheckCircleFilled />回答必须基于引用片段</span>
            <span><CheckCircleFilled />无可靠依据时明确拒答</span>
            <span><CheckCircleFilled />流程类问题过滤无关流程</span>
            <span><CheckCircleFilled />记录 prompt version 与模型信息</span>
            <span><CheckCircleFilled />管理员后端 RBAC 拦截模型配置写入</span>
          </div>
          {modelConfig && (
            <div className="config-readout">
              <span>Embedding：{modelConfig.embedding_model}</span>
              <span>最低证据分：{modelConfig.answer_min_score}</span>
              <span>Prompt：{modelConfig.prompt_version}</span>
            </div>
          )}
        </section>
      </div>
    </section>
  );
}

function EvalPage({ summary, logs }: { summary?: EvalSummary; logs: QALog[] }) {
  const data = summary || {
    case_count: 0,
    cases: [],
    log_count: logs.length,
    retrieval_hit_rate: 0,
    refusal_rate: 0,
    avg_latency_ms: 0,
    citation_rate: 0,
    recent_results: []
  };
  const metrics = [
    { title: '命中率', value: percent(data.retrieval_hit_rate), raw: data.retrieval_hit_rate, color: '#12805c' },
    { title: '拒答率', value: percent(data.refusal_rate), raw: data.refusal_rate, color: '#c2410c' },
    { title: '引用率', value: percent(data.citation_rate), raw: data.citation_rate, color: '#1d4ed8' },
    { title: '平均耗时', value: `${Math.round(data.avg_latency_ms)}ms`, raw: Math.min(data.avg_latency_ms / 3000, 1), color: '#7c3aed' }
  ];

  return (
    <section className="page-card">
      <div className="page-head">
        <div>
          <Title level={3}>RAG 评测面板</Title>
          <Text type="secondary">展示 eval cases、命中率、拒答率、平均耗时和引用率</Text>
        </div>
        <Tag>{data.case_count} 个评测用例</Tag>
      </div>

      <div className="eval-metrics">
        {metrics.map((metric) => (
          <section className="eval-metric" key={metric.title}>
            <span>{metric.title}</span>
            <strong>{metric.value}</strong>
            <div><i style={{ width: `${Math.max(metric.raw * 100, 4)}%`, background: metric.color }} /></div>
          </section>
        ))}
      </div>

      <div className="page-grid two">
        <section className="management-card">
          <div className="mini-title"><FileSearchOutlined />Eval Cases</div>
          {data.cases.length ? data.cases.map((item, index) => (
            <div className="eval-case-row" key={`${item.knowledge_base_id}-${index}`}>
              <strong>{item.question}</strong>
              <span>期望关键词：{item.expected_keyword || '未设置'} · KB：{item.knowledge_base_id}</span>
            </div>
          )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无评测用例" />}
        </section>
        <section className="management-card">
          <div className="mini-title"><NodeIndexOutlined />最近评测样本</div>
          {data.recent_results.length ? data.recent_results.slice(0, 6).map((log) => (
            <div className="qa-log-row" key={log.id}>
              <div>
                <strong>{log.question}</strong>
                <p>{log.answer}</p>
                <span>{log.latency_ms}ms · 引用 {log.citations.length} 条</span>
              </div>
              <Tag color={log.hit_knowledge_base ? 'green' : 'orange'}>{log.hit_knowledge_base ? '命中' : '拒答'}</Tag>
            </div>
          )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="问答后自动生成统计" />}
        </section>
      </div>
    </section>
  );
}

function LogsPage({
  logs,
  knowledgeBases,
  onOpenDetail
}: {
  logs: QALog[];
  knowledgeBases: KnowledgeBase[];
  onOpenDetail: (detail: AnswerDetail) => void;
}) {
  const [filterKbId, setFilterKbId] = useState('all');
  const visibleLogs = filterKbId === 'all' ? logs : logs.filter((log) => log.knowledge_base_id === filterKbId);
  return (
    <section className="page-card">
      <div className="page-head">
        <div>
          <Title level={3}>操作日志</Title>
          <Text type="secondary">查看问答历史、命中状态、耗时和模型信息</Text>
        </div>
        <Space>
          <Select
            value={filterKbId}
            className="log-filter"
            onChange={setFilterKbId}
            options={[
              { value: 'all', label: '全部知识库' },
              ...knowledgeBases.map((kb) => ({ value: kb.id, label: kb.name }))
            ]}
          />
          <Tag>{visibleLogs.length} 条记录</Tag>
        </Space>
      </div>
      <section className="management-card">
        {visibleLogs.length ? visibleLogs.map((log) => (
          <div className="qa-log-row" key={log.id}>
            <div>
              <strong>{log.question}</strong>
              <p>{log.answer}</p>
              <span>{dayjs(log.created_at).format('YYYY-MM-DD HH:mm')} · {log.model_name} · {log.latency_ms}ms</span>
            </div>
            <Space>
              <Tag color={log.hit_knowledge_base ? 'green' : 'orange'}>{log.hit_knowledge_base ? '命中' : '拒答'}</Tag>
              <Button size="small" onClick={() => onOpenDetail(detailFromLog(log))}>详情</Button>
            </Space>
          </div>
        )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无日志" />}
      </section>
    </section>
  );
}

function OverviewCard({ title, value, note, icon }: { title: string; value: string | number; note: string; icon: ReactNode }) {
  return (
    <section className="overview-card">
      <span>{icon}</span>
      <div>
        <em>{title}</em>
        <strong>{value}</strong>
        <small>{note}</small>
      </div>
    </section>
  );
}

function HistoryIcon() {
  return <FileSearchOutlined />;
}

function TopBar({
  currentUser,
  notificationCount,
  setActiveSection,
  onSearch,
  onHelp,
  onLogout
}: {
  currentUser: CurrentUser;
  notificationCount: number;
  setActiveSection: (section: SectionKey) => void;
  onSearch: (value: string) => void;
  onHelp: () => void;
  onLogout: () => void;
}) {
  const [search, setSearch] = useState('');
  const [profileOpen, setProfileOpen] = useState(false);
  const profileItems: MenuProps['items'] = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人资料',
      onClick: () => setProfileOpen(true)
    },
    {
      key: 'permissions',
      icon: <TeamOutlined />,
      label: '权限角色',
      onClick: () => setActiveSection('permissions')
    },
    {
      key: 'settings',
      icon: <SettingOutlined />,
      label: '系统设置',
      onClick: () => setActiveSection('settings')
    },
    {
      key: 'logs',
      icon: <FileTextOutlined />,
      label: '操作日志',
      onClick: () => setActiveSection('logs')
    },
    { type: 'divider' },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      danger: true,
      onClick: onLogout
    }
  ];

  return (
    <header className="top-bar">
      <Brand />
      <div className="global-search">
        <SearchOutlined />
        <input
          placeholder="输入问题并进入智能问答..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && search.trim()) onSearch(search.trim());
          }}
        />
        <kbd>⌘K</kbd>
      </div>
      <div className="top-actions">
        <button className="top-icon-button" onClick={() => setActiveSection('logs')} aria-label="查看通知和日志">
          <Badge count={notificationCount} size="small"><BellOutlined /></Badge>
        </button>
        <button className="top-icon-button" onClick={onHelp} aria-label="查看帮助">
          <QuestionCircleOutlined />
        </button>
        <Dropdown menu={{ items: profileItems }} trigger={['click']} placement="bottomRight">
          <button className="profile" aria-label="打开用户菜单">
            <Avatar src={currentUser.avatar || undefined}>{currentUser.name.slice(0, 1)}</Avatar>
            <div>
              <strong>{currentUser.name}</strong>
              <span>{currentUser.role_label}</span>
            </div>
            <MoreOutlined />
          </button>
        </Dropdown>
      </div>
      <Modal
        title="个人资料"
        open={profileOpen}
        onCancel={() => setProfileOpen(false)}
        footer={<Button type="primary" onClick={() => setProfileOpen(false)}>知道了</Button>}
      >
        <div className="profile-modal">
          <Avatar size={56} src={currentUser.avatar || undefined}>{currentUser.name.slice(0, 1)}</Avatar>
          <div>
            <h3>{currentUser.name}</h3>
            <p>{currentUser.role_label}</p>
          </div>
        </div>
        <div className="profile-detail-grid">
          <span>登录账号</span><strong>{currentUser.username}</strong>
          <span>账号角色</span><strong>{currentUser.role_label}</strong>
          <span>访问范围</span><strong>{currentUser.access_scope}</strong>
          <span>登录状态</span><strong>已登录</strong>
        </div>
      </Modal>
    </header>
  );
}

function Brand() {
  return (
    <div className="brand">
      <div className="brand-logo"><DatabaseOutlined /></div>
      <h1>企业知识库 RAG 问答平台</h1>
    </div>
  );
}

function NavItem({ icon, label, active, onClick }: { icon: ReactNode; label: string; active?: boolean; onClick: () => void }) {
  return (
    <button className={`nav-item ${active ? 'active' : ''}`} onClick={onClick}>
      {icon}
      <span>{label}</span>
    </button>
  );
}

function QuickAction({ icon, title, desc, disabled }: { icon: ReactNode; title: string; desc: string; disabled?: boolean }) {
  return (
    <button className="quick-action" disabled={disabled}>
      <span className="quick-icon">{icon}</span>
      <span><strong>{title}</strong><em>{desc}</em></span>
    </button>
  );
}

function EmptyState({ onAsk, disabled }: { onAsk: (question: string) => void; disabled: boolean }) {
  return (
    <div className="empty-chat">
      <RobotOutlined />
      <h3>选择知识库并上传文档后开始问答</h3>
      <p>系统会返回答案、证据来源、检索片段和问答日志。</p>
      <div>
        {sampleQuestions.map((item) => (
          <Button key={item} disabled={disabled} onClick={() => onAsk(item)}>{item}</Button>
        ))}
      </div>
    </div>
  );
}

function AnswerDetailModal({ detail, onClose }: { detail?: AnswerDetail; onClose: () => void }) {
  return (
    <Modal title={detail?.title || '问答详情'} open={Boolean(detail)} onCancel={onClose} footer={<Button type="primary" onClick={onClose}>关闭</Button>} width={860}>
      {detail && (
        <div className="detail-modal">
          {detail.question && (
            <section>
              <h3>问题</h3>
              <p>{detail.question}</p>
            </section>
          )}
          <section>
            <h3>答案</h3>
            <p>{detail.answer}</p>
            {detail.meta && <span>{detail.meta}</span>}
          </section>
          <section>
            <h3>引用证据</h3>
            {detail.citations.length ? detail.citations.map((item, index) => (
              <div className="detail-row" key={`${item.chunk_id}-${index}`}>
                <strong>{index + 1}. {item.document_name} · 片段 {item.chunk_index}</strong>
                <p>{item.snippet}</p>
                <Tag color="green">得分 {Math.round(item.score * 100)}%</Tag>
              </div>
            )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无引用证据" />}
          </section>
          <section>
            <h3>检索片段</h3>
            {detail.retrievalResults.length ? detail.retrievalResults.map((item, index) => (
              <div className="detail-row" key={`${item.chunk_id}-${index}`}>
                <strong>{index + 1}. {item.document_name} · {sourceText(item.sources)}</strong>
                <p>{item.content || (item.matched_terms?.length ? `命中词：${item.matched_terms.join('、')}` : '暂无片段摘要')}</p>
                <Space wrap>
                  <Tag>综合 {Math.round((item.final_score || 0) * 100)}%</Tag>
                  <Tag>向量 {Math.round((item.vector_score || 0) * 100)}%</Tag>
                  <Tag>关键词 {Math.round((item.keyword_score || 0) * 100)}%</Tag>
                </Space>
              </div>
            )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无检索片段" />}
          </section>
        </div>
      )}
    </Modal>
  );
}

function DocumentDetailModal({
  detail,
  loading,
  onClose
}: {
  detail?: { doc: DocumentItem; chunks: ChunkItem[] };
  loading: boolean;
  onClose: () => void;
}) {
  return (
    <Modal title={detail ? `文档切片：${detail.doc.filename}` : '文档切片'} open={Boolean(detail)} onCancel={onClose} footer={<Button type="primary" onClick={onClose}>关闭</Button>} width={860}>
      <Spin spinning={loading}>
        {detail && (
          <div className="detail-modal">
            <section>
              <h3>索引状态</h3>
              <Space wrap>
                <Tag color={statusColor(detail.doc.status)}>{statusText(detail.doc.status)}</Tag>
                <Tag>{detail.doc.chunk_count} 个切片</Tag>
                <Tag>{formatNumber(detail.doc.char_count)} 字符</Tag>
              </Space>
            </section>
            <section>
              <h3>切片列表</h3>
              {detail.chunks.length ? detail.chunks.map((chunk) => (
                <div className="detail-row" key={chunk.id}>
                  <strong>片段 {chunk.chunk_index} {chunk.page_number ? `· 第 ${chunk.page_number} 页` : ''}</strong>
                  <p>{chunk.content}</p>
                  <span>{chunk.char_length} 字符 · 约 {chunk.token_estimate} tokens</span>
                </div>
              )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无切片" />}
            </section>
          </div>
        )}
      </Spin>
    </Modal>
  );
}

function EvidenceGrid({
  latestAnswer,
  latestQuestion,
  documents,
  setActiveSection,
  onOpenDetail
}: {
  latestAnswer?: AskResponse;
  latestQuestion?: string;
  documents: DocumentItem[];
  setActiveSection: (section: SectionKey) => void;
  onOpenDetail: (detail: AnswerDetail) => void;
}) {
  const citations = latestAnswer?.citations || [];
  const retrieval = latestAnswer?.retrieval_results || [];
  const score = citations[0]?.score ? Math.round(citations[0].score * 100) : 0;
  const hasAnswer = Boolean(latestAnswer?.answer);

  return (
    <div className="evidence-grid">
      <InfoCard
        icon={<FileSearchOutlined />}
        title={`证据来源 (${hasAnswer ? citations.length : 0})`}
        footer={hasAnswer ? '查看本次证据 →' : '等待问答生成证据'}
        onFooter={hasAnswer ? () => onOpenDetail(detailFromAnswer(latestAnswer!, latestQuestion)) : undefined}
      >
        {hasAnswer && citations.length ? citations.slice(0, 4).map((item, index) => (
          <div className="rank-line" key={`${item.document_name}-${index}`}>
            <span>{index + 1}</span>
            <strong>{item.document_name}</strong>
            <em>{Math.round((item.score || 0) * 100)}%</em>
          </div>
        )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={hasAnswer ? '本次未返回证据' : '提问后展示真实证据'} />}
      </InfoCard>

      <InfoCard
        icon={<NodeIndexOutlined />}
        title={`检索片段 (${hasAnswer ? retrieval.length : 0})`}
        footer={hasAnswer ? '查看全部片段 →' : '等待检索结果'}
        onFooter={hasAnswer ? () => onOpenDetail(detailFromAnswer(latestAnswer!, latestQuestion)) : undefined}
      >
        {hasAnswer && retrieval.length ? retrieval.slice(0, 3).map((item, index) => (
          <div className="snippet-line" key={`${item.chunk_id}-${index}`}>
            <strong>片段 {index + 1} {item.sources ? sourceText(item.sources) : '语义匹配'}</strong>
            <p>{item.content || (item.matched_terms?.length ? `命中词：${item.matched_terms.slice(0, 5).join('、')}` : '无片段摘要')}</p>
            <span>相似度 {Math.round((item.final_score || 0) * 100)}%</span>
          </div>
        )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={hasAnswer ? '本次未返回片段' : '提问后展示真实片段'} />}
      </InfoCard>

      <InfoCard icon={<FileTextOutlined />} title={`相关文档 (${documents.length})`} footer="查看全部文档 →" onFooter={() => setActiveSection('ingest')}>
        {documents.slice(0, 4).map((doc) => (
          <div className="doc-line" key={doc.id}>
            {fileIcon(doc.filename)}
            <strong>{doc.filename}</strong>
          </div>
        ))}
        {!documents.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无文档" />}
      </InfoCard>

      <div className="confidence-card">
        <div className="mini-title"><SafetyCertificateOutlined />置信度</div>
        <Progress type="circle" percent={hasAnswer ? score : 0} strokeColor="#12805c" size={116} format={(value) => <><strong>{value}%</strong><span>{hasAnswer ? confidenceText(value || 0) : '待生成'}</span></>} />
        <p>{hasAnswer ? '基于本次检索证据与生成结果的综合评估' : '完成一次问答后展示真实置信度'}</p>
      </div>
    </div>
  );
}

function InfoCard({ icon, title, footer, children, onFooter }: { icon: ReactNode; title: string; footer: string; children: ReactNode; onFooter?: () => void }) {
  return (
    <section className="info-card">
      <div className="mini-title">{icon}{title}</div>
      <div className="info-body">{children}</div>
      <button className="link-button" disabled={!onFooter} onClick={onFooter}>{footer}</button>
    </section>
  );
}

function ModelPanel({
  currentUser,
  topK,
  setTopK,
  modelConfig,
  openSettings
}: {
  currentUser: CurrentUser;
  topK: number;
  setTopK: (value: number) => void;
  modelConfig?: ModelConfig;
  openSettings: () => void;
}) {
  const canConfigure = currentUser.role === 'admin';
  return (
    <section className="side-card model-card">
      <div className="side-card-head">
        <h3>模型设置</h3>
        <SettingOutlined />
      </div>
      <label>当前模型</label>
      <Select value={modelConfig?.chat_model || 'Mock Chat'} disabled={!canConfigure} options={[{ value: modelConfig?.chat_model || 'Mock Chat', label: modelConfig?.chat_model || 'Mock Chat' }]} />
      <label>检索策略</label>
      <Select value={topK} disabled={!canConfigure} onChange={setTopK} options={[4, 6, 8, 10, 12, 20].map((value) => ({ value, label: `混合检索（向量 + 关键词）Top ${value}` }))} />
      <button className="link-button" onClick={openSettings}>{canConfigure ? '高级设置 →' : '查看只读配置 →'}</button>
    </section>
  );
}

function HealthPanel({
  documents,
  totalChunks,
  totalChars,
  failedDocs,
  openIngest
}: {
  documents: DocumentItem[];
  totalChunks: number;
  totalChars: number;
  failedDocs: number;
  openIngest: () => void;
}) {
  const percent = documents.length ? Math.round(((documents.length - failedDocs) / documents.length) * 100) : 100;
  return (
    <section className="side-card health-card">
      <div className="mini-title"><DatabaseOutlined />知识库健康度</div>
      <span className="muted">更新于：今天 {dayjs().format('HH:mm')}</span>
      <div className="stat-pair">
        <div><span>文档总数</span><strong>{formatNumber(documents.length)}</strong></div>
        <div><span>知识点数</span><strong>{formatNumber(totalChunks)}</strong></div>
      </div>
      <div className="health-row"><span>健康状态</span><b>{failedDocs ? '需处理' : '正常'}</b></div>
      <Progress percent={percent} strokeColor="#12805c" showInfo />
      <button className="link-button" onClick={openIngest}>查看详情 →</button>
      <small>{formatNumber(totalChars)} 字符已索引</small>
    </section>
  );
}

function TrendPanel({ logs, latestAnswer }: { logs: QALog[]; latestAnswer?: AskResponse }) {
  const trend = buildTrendData(logs);
  const total = trend.reduce((sum, item) => sum + item.count, 0);
  const previous = trend.slice(0, 3).reduce((sum, item) => sum + item.count, 0);
  const recent = trend.slice(3).reduce((sum, item) => sum + item.count, 0);
  const change = previous ? Math.round(((recent - previous) / previous) * 100) : 0;
  const hitCount = logs.filter((item) => item.hit_knowledge_base).length;
  const hitRate = logs.length ? Math.round((hitCount / logs.length) * 1000) / 10 : 0;
  const points = buildTrendPoints(trend);
  return (
    <section className="side-card trend-card">
      <div className="mini-title"><NodeIndexOutlined />使用趋势 <span>（近7天）</span></div>
      <div className="stat-pair">
        <div><span>问答数</span><strong>{total}</strong><em>{formatChange(change)}</em></div>
        <div><span>命中率</span><strong>{hitRate}%</strong><em>{logs.length ? `${hitCount}/${logs.length}` : '0/0'}</em></div>
      </div>
      {total ? (
        <svg className="trend-chart" viewBox="0 0 320 120" aria-hidden="true">
          <polyline points={points.map((point) => `${point.x},${point.y}`).join(' ')} fill="none" stroke="#12805c" strokeWidth="4" />
          <g fill="#fff" stroke="#12805c" strokeWidth="4">
            {points.map((point) => <circle key={`${point.x}-${point.y}`} cx={point.x} cy={point.y} r="6" />)}
          </g>
        </svg>
      ) : (
        <div className="trend-empty">暂无近 7 天问答数据</div>
      )}
      <div className="trend-dates">{trend.map((item) => <span key={item.date}>{dayjs(item.date).format('MM-DD')}</span>)}</div>
      {latestAnswer && <small>最近响应：{latestAnswer.latency_ms}ms / {latestAnswer.model_name}</small>}
    </section>
  );
}

function buildTrendData(logs: QALog[]) {
  const days = Array.from({ length: 7 }, (_, index) => dayjs().subtract(6 - index, 'day').format('YYYY-MM-DD'));
  return days.map((date) => ({
    date,
    count: logs.filter((log) => dayjs(log.created_at).format('YYYY-MM-DD') === date).length
  }));
}

function buildTrendPoints(trend: Array<{ date: string; count: number }>) {
  const max = Math.max(...trend.map((item) => item.count), 1);
  return trend.map((item, index) => ({
    x: 16 + index * 48,
    y: 102 - (item.count / max) * 76
  }));
}

function formatChange(change: number) {
  if (change > 0) return `↑ ${change}%`;
  if (change < 0) return `↓ ${Math.abs(change)}%`;
  return '0%';
}

function RecentDocs({
  documents,
  canWriteDocuments,
  rebuildingDocId,
  onRebuild,
  openIngest
}: {
  documents: DocumentItem[];
  canWriteDocuments: boolean;
  rebuildingDocId?: string;
  onRebuild: (doc: DocumentItem) => void;
  openIngest: () => void;
}) {
  return (
    <section className="side-card recent-card">
      <div className="side-card-head">
        <div className="mini-title"><FileTextOutlined />最近上传文档</div>
        <button className="link-button" onClick={openIngest}>全部 →</button>
      </div>
      {documents.length ? documents.slice(0, 4).map((doc) => (
        <div className="recent-doc" key={doc.id}>
          {fileIcon(doc.filename)}
          <div>
            <strong>{doc.filename}</strong>
            <span>{doc.status === 'completed' ? '已索引' : statusText(doc.status)}</span>
          </div>
          <Tooltip title="重建索引">
            <Button
              size="small"
              type="text"
              icon={<ReloadOutlined />}
              disabled={!canWriteDocuments}
              loading={rebuildingDocId === doc.id}
              onClick={() => onRebuild(doc)}
            />
          </Tooltip>
        </div>
      )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无文档" />}
    </section>
  );
}

function fileIcon(filename: string) {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.pdf')) return <FilePdfOutlined className="file-icon pdf" />;
  if (lower.endsWith('.ppt') || lower.endsWith('.pptx')) return <FilePptOutlined className="file-icon ppt" />;
  if (lower.endsWith('.xls') || lower.endsWith('.xlsx')) return <FileExcelOutlined className="file-icon xls" />;
  return <FileTextOutlined className="file-icon doc" />;
}

function detailFromAnswer(answer: AskResponse, question?: string): AnswerDetail {
  return {
    title: '本次问答详情',
    question,
    answer: answer.answer,
    citations: answer.citations || [],
    retrievalResults: answer.retrieval_results || [],
    meta: `${answer.model_name || '未知模型'} · ${answer.latency_ms}ms · Prompt ${answer.prompt_version || '-'}`
  };
}

function detailFromLog(log: QALog): AnswerDetail {
  return {
    title: '日志详情',
    question: log.question,
    answer: log.answer,
    citations: log.citations || [],
    retrievalResults: log.retrieval_results?.items || [],
    meta: `${dayjs(log.created_at).format('YYYY-MM-DD HH:mm')} · ${log.model_name} · ${log.latency_ms}ms`
  };
}

function confidenceText(value: number) {
  if (value >= 80) return '高置信度';
  if (value >= 50) return '中置信度';
  if (value > 0) return '低置信度';
  return '无证据';
}

function statusColor(status: DocumentItem['status']) {
  if (status === 'completed') return 'green';
  if (status === 'failed') return 'red';
  if (status === 'processing') return 'blue';
  return 'default';
}

function statusText(status: DocumentItem['status']) {
  if (status === 'completed') return '已完成';
  if (status === 'failed') return '失败';
  if (status === 'processing') return '处理中';
  return '待处理';
}

function sourceText(sources: string) {
  return sources
    .replace('keyword_like', '关键词模糊')
    .replace('keyword', '关键词')
    .replace('vector', '向量');
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value);
}

function percent(value: number) {
  return `${Math.round(value * 1000) / 10}%`;
}

export default App;
