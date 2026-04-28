# Chart SQL Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 WrenAI 中新增 Chart SQL 页面，支持 SQL 执行 + ECharts 图表渲染，通过容器化的 chart-engine 服务提供图表生成能力。

**Architecture:** chart-engine 作为第 7 个 Docker 容器加入 WrenAI 编排。wren-ui 新增 `/api/v1/chart_engine` API route 代理请求到 chart-engine 容器。前端新增 `/chart-sql` 页面，上半部分 SQL Editor + 问题输入，下半部分 Table/Chart 双 Tab。

**Tech Stack:** Python 3.12 (chart-engine container), Next.js 14 (wren-ui), Ant Design, ECharts, styled-components, Docker Compose

---

## File Structure

```
data-agent/
├── chart_engine/
│   └── Dockerfile                                  # 新建 — chart-engine 容器镜像

WrenAI/
├── docker/
│   ├── docker-compose.yaml                         # 修改 — 加 chart-engine service
│   ├── .env                                        # 修改 — 加 CHART_ENGINE 变量
│   └── .env.example                                # 修改 — 加 CHART_ENGINE 变量
├── wren-ui/src/
│   ├── utils/enum/path.ts                          # 修改 — 加 ChartSQL 路径
│   ├── components/HeaderBar.tsx                    # 修改 — 加导航按钮
│   ├── pages/chart-sql.tsx                         # 新建 — Chart SQL 页面
│   └── pages/api/v1/chart_engine.ts               # 新建 — API route 代理
```

---

### Task 1: chart-engine Dockerfile

**Files:**
- Create: `data-agent/chart_engine/Dockerfile`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# chart_engine/Dockerfile
FROM python:3.12.0-slim-bookworm

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY pyproject.toml ./

# 安装 Python 依赖（只装 chart-engine 需要的）
RUN pip install --no-cache-dir \
    litellm \
    fastapi \
    uvicorn \
    pydantic \
    python-dateutil \
    pyyaml \
    duckdb

# 复制应用代码
COPY . /app/chart_engine_src/
ENV PYTHONPATH="/app/chart_engine_src"

EXPOSE 8100

CMD ["python", "-m", "uvicorn", "chart_engine.server:app", "--host", "0.0.0.0", "--port", "8100"]
```

- [ ] **Step 2: 验证 Dockerfile 可以构建**

Run: `cd /Users/songruikang/Research/data-agent && docker build -t chart-engine:latest -f chart_engine/Dockerfile .`
Expected: 构建成功

- [ ] **Step 3: 验证容器可以启动**

Run: `docker run --rm -p 8100:8100 chart-engine:latest &` 然后 `curl http://localhost:8100/health`
Expected: `{"status":"ok"}`

- [ ] **Step 4: Commit**

```bash
cd /Users/songruikang/Research/data-agent
git add chart_engine/Dockerfile
git commit -m "feat(chart-engine): Dockerfile 容器化"
```

---

### Task 2: Docker Compose 集成

**Files:**
- Modify: `WrenAI/docker/docker-compose.yaml`
- Modify: `WrenAI/docker/.env`

- [ ] **Step 1: 在 docker-compose.yaml 的 wren-ui service 之前添加 chart-engine service**

在 `qdrant:` service 之后、`wren-ui:` service 之前，添加：

```yaml
  chart-engine:
    # [自定义] 图表生成引擎 — SQL 查询结果 → ECharts option JSON
    image: chart-engine:latest
    build:
      context: ../../chart_engine
      dockerfile: Dockerfile
    restart: on-failure
    platform: ${PLATFORM}
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
    expose:
      - ${CHART_ENGINE_PORT}
    environment:
      CHART_LLM_MODEL: ${CHART_LLM_MODEL:-ollama_chat/qwen3:32b}
      CHART_LLM_API_BASE: ${CHART_LLM_API_BASE:-http://10.220.239.55:11343}
    networks:
      - wren
```

- [ ] **Step 2: 在 wren-ui 的 environment 中添加 CHART_ENGINE_ENDPOINT**

在 wren-ui service 的 environment 部分添加：

```yaml
      CHART_ENGINE_ENDPOINT: http://chart-engine:${CHART_ENGINE_PORT}
```

- [ ] **Step 3: 在 .env 文件末尾添加 chart-engine 变量**

```
# chart-engine
CHART_ENGINE_PORT=8100
CHART_LLM_MODEL=ollama_chat/qwen3:32b
CHART_LLM_API_BASE=http://10.220.239.55:11343
```

- [ ] **Step 4: Commit**

```bash
cd /Users/songruikang/Research/data-agent/WrenAI
git add docker/docker-compose.yaml docker/.env
git commit -m "feat(docker): 添加 chart-engine 容器编排"
```

---

### Task 3: Next.js API Route — chart_engine 代理

**Files:**
- Create: `WrenAI/wren-ui/src/pages/api/v1/chart_engine.ts`

- [ ] **Step 1: 创建 API route**

```typescript
// WrenAI/wren-ui/src/pages/api/v1/chart_engine.ts
import { NextApiRequest, NextApiResponse } from 'next';
import axios from 'axios';
import { getLogger } from '@server/utils';

const logger = getLogger('API_CHART_ENGINE');

const CHART_ENGINE_ENDPOINT =
  process.env.CHART_ENGINE_ENDPOINT || 'http://localhost:8100';

interface ChartEngineRequest {
  question: string;
  sql: string;
  data: Record<string, unknown>[];
}

interface ChartEngineResponse {
  chart_type: string;
  echarts_option: Record<string, unknown>;
  reasoning: string;
  warnings: string[];
  fallback: boolean;
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse,
) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { question, sql, data } = req.body as ChartEngineRequest;

  if (!question || !data) {
    return res.status(400).json({ error: 'question and data are required' });
  }

  try {
    const response = await axios.post<ChartEngineResponse>(
      `${CHART_ENGINE_ENDPOINT}/generate`,
      { question, sql: sql || '', data },
      { timeout: 120000, headers: { 'Content-Type': 'application/json' } },
    );

    return res.status(200).json(response.data);
  } catch (error) {
    logger.error('Chart engine error:', error?.message || error);

    // chart-engine 不可用时，返回 mock 模式提示
    if (error?.code === 'ECONNREFUSED' || error?.code === 'ENOTFOUND') {
      return res.status(503).json({
        error: 'Chart engine service is not available',
        hint: 'Run: python -m chart_engine serve --port 8100',
      });
    }

    return res.status(500).json({
      error: error?.response?.data?.detail || error?.message || 'Unknown error',
    });
  }
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/songruikang/Research/data-agent/WrenAI
git add wren-ui/src/pages/api/v1/chart_engine.ts
git commit -m "feat(wren-ui): chart_engine API route 代理"
```

---

### Task 4: 路由 + 导航按钮

**Files:**
- Modify: `WrenAI/wren-ui/src/utils/enum/path.ts`
- Modify: `WrenAI/wren-ui/src/components/HeaderBar.tsx`

- [ ] **Step 1: 在 path.ts 添加路由**

在 `Logs = '/logs',` 之后添加：

```typescript
  ChartSQL = '/chart-sql',
```

- [ ] **Step 2: 在 HeaderBar.tsx 添加导航按钮**

在 SQL 按钮（`Path.QuerySQL` 那个 StyledButton）之后、Logs 按钮之前，添加：

```tsx
              <StyledButton
                shape="round"
                size="small"
                $isHighlight={pathname.startsWith(Path.ChartSQL)}
                onClick={() => router.push(Path.ChartSQL)}
              >
                Chart SQL
              </StyledButton>
```

- [ ] **Step 3: Commit**

```bash
cd /Users/songruikang/Research/data-agent/WrenAI
git add wren-ui/src/utils/enum/path.ts wren-ui/src/components/HeaderBar.tsx
git commit -m "feat(wren-ui): Chart SQL 路由和导航按钮"
```

---

### Task 5: Chart SQL 页面

**Files:**
- Create: `WrenAI/wren-ui/src/pages/chart-sql.tsx`

- [ ] **Step 1: 创建完整页面**

```tsx
// WrenAI/wren-ui/src/pages/chart-sql.tsx
import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Button,
  Input,
  Switch,
  Tabs,
  Table,
  Space,
  Spin,
  Alert,
  message,
  Typography,
} from 'antd';
import styled from 'styled-components';
import PlayCircleOutlined from '@ant-design/icons/PlayCircleOutlined';
import ClearOutlined from '@ant-design/icons/ClearOutlined';
import SiderLayout from '@/components/layouts/SiderLayout';

const { TextArea } = Input;
const { Text } = Typography;

// ─── Styles ──────────────────────────────────────────────────────

const Container = styled.div`
  display: flex;
  flex-direction: column;
  height: calc(100vh - 48px);
  padding: 16px 24px;
  overflow: hidden;
  background: #f5f5f5;
`;

const EditorSection = styled.div`
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
`;

const ResultSection = styled.div`
  flex: 1;
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  overflow: hidden;
  display: flex;
  flex-direction: column;
`;

const ToolbarRow = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
`;

const ChartContainer = styled.div`
  width: 100%;
  height: 100%;
  min-height: 400px;
`;

const StyledTextArea = styled(TextArea)`
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
`;

const StatusBar = styled.div`
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 12px;
  color: #666;
  margin-top: 8px;
`;

// ─── Types ───────────────────────────────────────────────────────

interface Column {
  name: string;
  type: string;
}

interface SqlResult {
  records: Record<string, unknown>[];
  columns: Column[];
  totalRows: number;
}

interface ChartResult {
  chart_type: string;
  echarts_option: Record<string, unknown>;
  reasoning: string;
  warnings: string[];
  fallback: boolean;
}

// ─── Component ───────────────────────────────────────────────────

export default function ChartSqlPage() {
  // State
  const [sql, setSql] = useState('');
  const [question, setQuestion] = useState('');
  const [chartMode, setChartMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [sqlResult, setSqlResult] = useState<SqlResult | null>(null);
  const [chartResult, setChartResult] = useState<ChartResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('table');
  const [duration, setDuration] = useState(0);

  const chartRef = useRef<HTMLDivElement>(null);
  const echartsInstance = useRef<any>(null);

  // 渲染 ECharts
  const renderChart = useCallback((option: Record<string, unknown>) => {
    if (!chartRef.current) return;

    // 动态加载 echarts（避免 SSR 问题）
    import('echarts').then((echarts) => {
      if (echartsInstance.current) {
        echartsInstance.current.dispose();
      }
      const chart = echarts.init(chartRef.current);
      chart.setOption(option as any);
      echartsInstance.current = chart;

      // 响应窗口大小变化
      const handleResize = () => chart.resize();
      window.addEventListener('resize', handleResize);
      return () => window.removeEventListener('resize', handleResize);
    });
  }, []);

  // chart result 变化时重新渲染
  useEffect(() => {
    if (
      chartResult?.echarts_option &&
      !chartResult.echarts_option.table &&
      !chartResult.echarts_option.kpi_card &&
      activeTab === 'chart'
    ) {
      renderChart(chartResult.echarts_option);
    }
  }, [chartResult, activeTab, renderChart]);

  // tab 切换到 chart 时渲染
  useEffect(() => {
    if (activeTab === 'chart' && chartResult?.echarts_option) {
      // 延迟渲染，等 DOM 更新
      setTimeout(() => {
        if (
          chartResult.echarts_option &&
          !chartResult.echarts_option.table &&
          !chartResult.echarts_option.kpi_card
        ) {
          renderChart(chartResult.echarts_option);
        }
      }, 100);
    }
  }, [activeTab, chartResult, renderChart]);

  // 清理 echarts 实例
  useEffect(() => {
    return () => {
      if (echartsInstance.current) {
        echartsInstance.current.dispose();
      }
    };
  }, []);

  // 执行 SQL
  const handleExecute = async () => {
    if (!sql.trim()) {
      message.warning('请输入 SQL');
      return;
    }
    if (chartMode && !question.trim()) {
      message.warning('Chart 模式需要填写问题');
      return;
    }

    setLoading(true);
    setError(null);
    setSqlResult(null);
    setChartResult(null);
    const startTime = Date.now();

    try {
      // Step 1: 执行 SQL
      const sqlRes = await fetch('/api/v1/run_sql', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sql: sql.trim(), limit: 1000 }),
      });

      if (!sqlRes.ok) {
        const errData = await sqlRes.json();
        throw new Error(errData.message || errData.error || `SQL 执行失败 (${sqlRes.status})`);
      }

      const sqlData: SqlResult = await sqlRes.json();
      setSqlResult(sqlData);
      setDuration(Date.now() - startTime);

      // Step 2: 如果 Chart 模式，调 chart-engine
      if (chartMode && sqlData.records.length > 0) {
        const chartRes = await fetch('/api/v1/chart_engine', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question: question.trim(),
            sql: sql.trim(),
            data: sqlData.records,
          }),
        });

        if (!chartRes.ok) {
          const errData = await chartRes.json();
          // chart-engine 失败不阻塞，table 结果已有
          message.warning(
            `图表生成失败: ${errData.error || errData.hint || '未知错误'}`,
          );
        } else {
          const chartData: ChartResult = await chartRes.json();
          setChartResult(chartData);
          setActiveTab('chart');

          if (chartData.warnings?.length > 0) {
            message.info(chartData.warnings.join('；'));
          }
        }
      }

      setDuration(Date.now() - startTime);
      if (!chartMode) {
        setActiveTab('table');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  // 清空
  const handleClear = () => {
    setSql('');
    setQuestion('');
    setSqlResult(null);
    setChartResult(null);
    setError(null);
    setDuration(0);
    if (echartsInstance.current) {
      echartsInstance.current.dispose();
      echartsInstance.current = null;
    }
  };

  // Ctrl+Enter 快捷执行
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleExecute();
    }
  };

  // Table 列定义
  const tableColumns = sqlResult?.columns?.map((col) => ({
    title: col.name,
    dataIndex: col.name,
    key: col.name,
    ellipsis: true,
    width: 150,
    render: (value: unknown) => {
      if (value === null || value === undefined) {
        return <Text type="secondary" italic>NULL</Text>;
      }
      return String(value);
    },
  })) || [];

  // KPI 卡片渲染
  const renderKpiCard = () => {
    if (!chartResult?.echarts_option?.kpi_card) return null;
    const opt = chartResult.echarts_option;
    return (
      <div style={{ textAlign: 'center', padding: '60px 20px' }}>
        <div style={{ fontSize: 56, fontWeight: 'bold', color: '#5470c6' }}>
          {String(opt.value ?? 0)}
        </div>
        <div style={{ fontSize: 16, color: '#666', marginTop: 8 }}>
          {String(opt.title ?? '')} {String(opt.unit ?? '')}
        </div>
      </div>
    );
  };

  // Chart tab 内容
  const renderChartContent = () => {
    if (!chartResult) {
      return (
        <div style={{ textAlign: 'center', padding: 60, color: '#999' }}>
          开启 Chart 模式并执行 SQL 后，图表将在这里显示
        </div>
      );
    }

    if (chartResult.echarts_option?.kpi_card) {
      return renderKpiCard();
    }

    if (chartResult.echarts_option?.table || chartResult.fallback) {
      return (
        <Alert
          type="info"
          message="数据不适合图表展示，已切换到表格视图"
          description={chartResult.reasoning}
          showIcon
          style={{ marginBottom: 16 }}
        />
      );
    }

    return <ChartContainer ref={chartRef} />;
  };

  return (
    <SiderLayout loading={false}>
      <Container>
        {/* 编辑区 */}
        <EditorSection>
          <ToolbarRow>
            <Space size={12} style={{ flex: 1 }}>
              <Switch
                checked={chartMode}
                onChange={setChartMode}
                checkedChildren="Chart"
                unCheckedChildren="SQL"
              />
              {chartMode && (
                <Input
                  placeholder="输入问题（如：各厂商设备数量对比）"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  style={{ width: 400 }}
                  onKeyDown={handleKeyDown}
                />
              )}
            </Space>
            <Space>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                onClick={handleExecute}
                loading={loading}
              >
                执行 {chartMode ? '+ 画图' : ''}
              </Button>
              <Button icon={<ClearOutlined />} onClick={handleClear}>
                清空
              </Button>
            </Space>
          </ToolbarRow>

          <StyledTextArea
            rows={6}
            placeholder="输入 SQL 语句... (Ctrl+Enter 执行)"
            value={sql}
            onChange={(e) => setSql(e.target.value)}
            onKeyDown={handleKeyDown}
          />

          {(sqlResult || error) && (
            <StatusBar>
              {sqlResult && (
                <>
                  <span>✅ {sqlResult.totalRows} 行</span>
                  <span>⏱ {duration}ms</span>
                  {chartResult && (
                    <span>📊 {chartResult.chart_type}</span>
                  )}
                </>
              )}
              {error && <span style={{ color: '#cf1322' }}>❌ 错误</span>}
            </StatusBar>
          )}
        </EditorSection>

        {/* 结果区 */}
        <ResultSection>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 60 }}>
              <Spin size="large" tip={chartMode ? '执行 SQL + 生成图表...' : '执行 SQL...'} />
            </div>
          ) : error ? (
            <Alert
              type="error"
              message="执行错误"
              description={error}
              showIcon
              style={{ margin: '20px 0' }}
            />
          ) : (
            <Tabs
              activeKey={activeTab}
              onChange={setActiveTab}
              style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
              items={[
                {
                  key: 'table',
                  label: `📊 Table${sqlResult ? ` (${sqlResult.totalRows})` : ''}`,
                  children: sqlResult ? (
                    <div style={{ overflow: 'auto', flex: 1 }}>
                      <Table
                        columns={tableColumns}
                        dataSource={sqlResult.records.map((r, i) => ({
                          ...r,
                          key: i,
                        }))}
                        size="small"
                        pagination={{ pageSize: 50, showSizeChanger: true }}
                        scroll={{ x: 'max-content' }}
                        bordered
                      />
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: 60, color: '#999' }}>
                      输入 SQL 并点击执行
                    </div>
                  ),
                },
                {
                  key: 'chart',
                  label: `📈 Chart${chartResult ? ` (${chartResult.chart_type})` : ''}`,
                  children: renderChartContent(),
                },
              ]}
            />
          )}
        </ResultSection>
      </Container>
    </SiderLayout>
  );
}
```

- [ ] **Step 2: 安装 echarts 依赖**

Run: `cd /Users/songruikang/Research/data-agent/WrenAI/wren-ui && yarn add echarts`

- [ ] **Step 3: 验证页面可以加载**

Run: `cd /Users/songruikang/Research/data-agent/WrenAI/wren-ui && yarn dev`
然后浏览器访问 `http://localhost:3000/chart-sql`
Expected: 页面正常显示，有 SQL 编辑器和 Chart 开关

- [ ] **Step 4: Commit**

```bash
cd /Users/songruikang/Research/data-agent/WrenAI
git add wren-ui/src/pages/chart-sql.tsx wren-ui/package.json wren-ui/yarn.lock
git commit -m "feat(wren-ui): Chart SQL 页面（SQL执行 + ECharts 图表）"
```

---

### Task 6: 端到端验证

- [ ] **Step 1: 本地启动 chart-engine 服务**

Run:
```bash
cd /Users/songruikang/Research/data-agent
.venv/bin/python -m chart_engine serve --port 8100 &
```

验证：`curl http://localhost:8100/health` → `{"status":"ok"}`

- [ ] **Step 2: 启动 WrenAI 开发服务器**

Run:
```bash
cd /Users/songruikang/Research/data-agent/WrenAI/wren-ui
CHART_ENGINE_ENDPOINT=http://localhost:8100 yarn dev
```

- [ ] **Step 3: 浏览器测试 SQL 模式**

1. 访问 `http://localhost:3000/chart-sql`
2. 输入 `SELECT 1 as test_value`
3. 点击"执行"
4. 下方 Table tab 应显示一行数据

- [ ] **Step 4: 浏览器测试 Chart 模式**

1. 开启 Chart 开关
2. 问题输入：`各厂商设备数量`
3. SQL 输入：`SELECT vendor, COUNT(*) as device_count FROM t_network_element WHERE role='PE' GROUP BY vendor`
4. 点击"执行 + 画图"
5. 下方应自动切到 Chart tab，显示 ECharts 柱状图

- [ ] **Step 5: Commit 最终状态**

```bash
cd /Users/songruikang/Research/data-agent
git add -A
git commit -m "feat: Chart SQL 页面端到端验证通过"
```
