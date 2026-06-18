#  轻量化规划AI总师协同平台

基于大语言模型的城市规划分析平台，融合 DeepSeek LLM、LangGraph Agent、计算机视觉、投入产出（IO）产业关联模型、Dify 知识库与高德地图，为城市规划专业人员提供图纸智能解析、用地面积计算、产业链分析、企业空间数据可视化、规划文本问答等一站式服务。

## 核心功能

### 图纸智能解析
- 上传规划图纸（PNG/JPG/WEBP），自动调用视觉 LLM 识别图例与比例尺
- 图例颜色自动校准：基于图像直方图分析，将 LLM 返回的颜色映射到图纸上实际存在的颜色
- 比例尺自动检测：检测比例尺标尺线段，结合文字信息计算 `meters_per_pixel`
- 支持手动校正比例尺和重新校准图例

### 用地面积计算
- 在图纸上绘制多边形或圆形选区，指定分析区域
- 基于图例颜色匹配，逐像素统计各类用地面积（平方米/公顷）
- 颜色容差可配置（默认 35），提供详细的匹配统计与调试信息

### 三种对话模式（按场景路由）

前端在对话区切换三种模式，每种模式走不同的后端 task_hint 与工具链：

- **数据分析（analysis）**：圈选范围 + 图纸规则。面积统计走 `计算面积`，其余走 `数据分析问答`，由 LangGraph Agent 自动选择工具（面积/地图/知识库）。
- **知识库问答（knowledge）**：规划文本检索问答。`规划文本问答`（无图）或 `图纸+规则综合分析`（带图）路由到 Dify 知识库应用，支持 SSE 流式返回知识库依据。
- **企业关联（industry）**：产业链与空间企业分析。前端 `resolveIndustryTaskHint` 把问题进一步细分为：
  - `企业统计`：纯统计问题（企业数量/类型/分布），本地直接生成分类统计
  - `企业关联分析`：含明确产业名 + 判断词（"是否适合""招商条件""具备基础"等），走 `industry_relation_tool` + judgment prompt
  - `产业发展方向分析`：无明确产业的方向问法（"应该发展什么""主导产业""招商方向"等），走 `industry_direction_tool` 多维评分

### 产业链分析（industry_relation_tool）
- 把用户产业名映射到 IO（投入产出）部门，查上下游关联产业
- 在地图圈选范围/bbox 内统计目标产业、上游、下游企业数与具体企业清单
- 同一企业按优先级 target > upstream > downstream 唯一归类
- 返回结果驱动前端给企业点按 relation 字段着色：
  - 红色（目标产业）、绿色（上游）、橙色（下游）、蓝色（其他）
- 后端 LLM 根据问题类型自动选择 prompt：
  - judgment（是否适合/可行性）→ 综合判断 + 优势/短板/建议
  - report（默认）→ 产业定位/链结构/基础/优势/短板/规划建议

### 区域产业发展方向评分（industry_direction_tool）
- 必须提供地图范围（圈选 selection 优先，其次 bbox，都没有则提示用户）
- 候选产业筛选：count ≥ 3 进入正式评分（Top10），count ∈ {1,2} 进入 `potential_clues` 不参与排名
- 五维评分模型（权重）：
  - 产业基础 0.20（归一化量级 × 0.6 + 基础分级 × 0.4）
  - 产业关联度 0.25
  - 产业链完整度 0.25（上下游配套企业覆盖率）
  - 企业集聚度 0.15（家/km²）
  - 服务配套 0.15（区域内服务类 POI 数）
- 归一化采用 `_segment_normalize`：样本充足时用 log1p min-max；候选 < 3 或差距过小时切换到绝对阈值（避免小样本失真）
- 基础分级（绝对企业数）：≥10 形成初步集聚 / 5-9 具备一定基础 / 3-4 基础较弱 / 1-2 潜力线索
- 推荐分级：重点推荐 / 谨慎推荐 / 潜力观察 / 暂不建议（分数与基础分级共同决定）
- 每个产业返回 `foundation_level`、`recommendation_level`、`reason`、`chain_completeness` 等定性字段，LLM 据此组织报告

### 高德地图集成
- 地图作为工作台主视觉中心，支持缩放/平移
- 三种圈选工具：多边形、矩形、圆形（selection 优先于 bbox 用于空间过滤）
- 在地图上叠加：企业点位（按产业关联着色）、POI（按类别）、土地利用图层、图纸信息图层
- 图层控制面板位于左侧，含基础底图、企业数据、POI 数据的可折叠树形结构

### 企业与空间数据
- 内置佛山市企业地理数据，支持按地理范围 / 区县 / 关键词查询
- 企业详情查看：经营状态、注册资本、经营范围等
- POI 兴趣点查询，支持按类别过滤
- 土地利用 GeoJSON 数据集可视化

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.0 |
| 数据库 | SQLite（图纸库 + 企业库，双库分离） |
| LLM | DeepSeek（通过 LangChain + LangGraph 集成） |
| 知识库 | Dify Chat 应用（规划文本问答 + 图片综合分析） |
| 产业关联模型 | 国民经济 IO 投入产出矩阵（io_service） |
| 图像处理 | Pillow + NumPy |
| 坐标转换 | pyproj |
| 数据验证 | Pydantic v2 + pydantic-settings |
| 前端框架 | React 18 + TypeScript |
| 构建工具 | Vite 5 |
| 地图 | 高德地图 JS API 2.0 |

## 项目结构

```
LLM_Lian/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI 入口，路由注册与 CORS 中间件
│   │   ├── core/
│   │   │   ├── config.py            # 全局配置（Pydantic Settings + 自动填充）
│   │   │   ├── database.py          # 数据库引擎与 Session 管理（双库）
│   │   │   └── security.py          # 文件类型校验
│   │   ├── models/
│   │   │   ├── diagram.py           # 图纸数据模型
│   │   │   ├── company.py           # 企业数据模型
│   │   │   └── poi.py               # POI 数据模型
│   │   ├── schemas/
│   │   │   ├── diagram.py           # 图纸 Pydantic Schema
│   │   │   ├── company.py           # 企业 Schema
│   │   │   ├── poi.py               # POI Schema
│   │   │   └── qa.py                # 问答请求/响应 Schema（含 map_bbox / map_selection）
│   │   ├── api/
│   │   │   ├── diagrams.py          # 图纸 API
│   │   │   ├── companies.py         # 企业查询 API
│   │   │   ├── pois.py              # POI 查询 API
│   │   │   ├── land_use.py          # 土地利用 API
│   │   │   └── qa.py                # 智能问答 API（含 task_hint 路由分发）
│   │   ├── services/
│   │   │   ├── diagram_service.py   # 图纸上传与处理编排
│   │   │   ├── agent_service.py     # LangGraph Agent 工作流（条件路由 + industry/direction 分支）
│   │   │   ├── llm_service.py       # LLM 调用（分类/合成/流式/视觉 + industry 三种 prompt）
│   │   │   ├── dify_chat_service.py # Dify 知识库对话集成（含图片上传）
│   │   │   ├── io_service.py        # IO 投入产出矩阵 + 行业映射 + 空间过滤
│   │   │   ├── legend_service.py    # 图例颜色校准算法
│   │   │   ├── scale_service.py     # 比例尺检测算法
│   │   │   ├── company_service.py   # 企业数据查询
│   │   │   ├── poi_service.py       # POI 数据管理
│   │   │   └── land_use_service.py  # 土地利用数据加载
│   │   └── tools/
│   │       ├── area_calculation.py  # 用地面积计算（像素级颜色分类）
│   │       ├── amap.py              # 高德地图工具
│   │       ├── knowledge_base.py    # 知识库工具（预留）
│   │       ├── industry_relation.py # 产业链关联工具（target/upstream/downstream 分类）
│   │       └── industry_direction.py# 产业发展方向评分工具（五维模型 + 分级推荐）
│   ├── scripts/
│   │   ├── init_companies.py        # 企业/POI 数据导入脚本
│   │   └── init_io_table.py         # IO 投入产出表导入脚本
│   ├── requirements.txt
│   └── .env                         # 环境变量配置
├── frontend/
│   ├── src/
│   │   ├── App.tsx                  # 主应用（三栏布局：图纸与图层库 / 工作台 / 对话）
│   │   ├── api/
│   │   │   └── client.ts            # API 客户端（含 SSE 流式处理）
│   │   ├── types/
│   │   │   └── index.ts             # TypeScript 类型定义
│   │   ├── styles.css               # 全局样式
│   │   └── main.tsx                 # 应用入口
│   ├── index.html                   # HTML 入口（含高德地图 SDK）
│   ├── vite.config.ts               # Vite 配置（API 代理）
│   └── package.json
├── data/                            # 运行时数据（数据库/上传/GeoJSON）
├── 企业数据/                         # 佛山市企业 CSV 数据
└── 图纸/                            # 示例图纸
```

## 快速开始

### 环境要求

- Python 3.12+（Conda 推荐）
- Node.js 18+

### 1. 配置环境变量

```bash
cd backend
cp .env.example .env
```

编辑 `backend/.env`，填写必要配置：

```env
# LLM 配置 — 直接填写 DeepSeek 即可，会自动填充 LLM_* 字段
DEEPSEEK_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_MODEL=deepseek-chat

# 如需覆盖，可单独指定（优先级高于 DEEPSEEK_*）
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=your_api_key
LLM_MODEL=deepseek-chat
LLM_VISION_MODEL=deepseek-chat

# Dify 知识库对话平台（用于知识库问答模式 + 图片综合分析）
DIFY_BASE_URL=https://api.dify.ai/v1
DIFY_API_KEY=app-xxxxxxxxxxxxxxxxx
DIFY_TASK_HINT=图纸+规则综合分析
DIFY_QUESTION_FIELD=question
DIFY_SHAPE_FIELD=shape
DIFY_DIAGRAM_ID_FIELD=diagram_id

# 高德地图
AMAP_API_KEY=your_amap_key

# 数据库与存储
DATABASE_URL=sqlite:///./data/app.db
COMPANY_DATABASE_URL=sqlite:///./data/companies.db
UPLOAD_DIR=./data/uploads
PROCESSED_DIR=./data/processed
LAND_USE_GEOJSON_PATH=./data/land_use.geojson
```

> 配置系统支持 `DEEPSEEK_*` 字段自动填充 `LLM_*` 字段（当后者为空时）。

### 2. 启动后端

```bash
# 使用 Conda（推荐）
conda create -n Lian python=3.12
conda activate Lian
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. 导入企业与 POI 数据（可选）

```bash
cd backend
python -m scripts.init_companies
python -m scripts.init_io_table   # 导入 IO 投入产出矩阵
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173 即可使用。

### 5. 验证服务

```bash
curl http://localhost:8000/api/health
# 返回: {"status":"ok","app":"Planning AI Platform"}
```

## API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/diagrams` | 上传图纸 |
| GET | `/api/diagrams` | 获取图纸列表 |
| GET | `/api/diagrams/{id}` | 获取图纸详情 |
| GET | `/api/diagrams/{id}/image` | 获取图纸图片 |
| PATCH | `/api/diagrams/{id}` | 重命名图纸 |
| DELETE | `/api/diagrams/{id}` | 删除图纸 |
| POST | `/api/diagrams/{id}/recalibrate-legend` | 重新校准图例 |
| POST | `/api/diagrams/{id}/calibrate-scale` | 校正比例尺 |
| POST | `/api/qa/ask` | 智能问答（同步） |
| POST | `/api/qa/ask/stream` | 智能问答（SSE 流式） |
| GET | `/api/companies` | 按地理范围查询企业 |
| GET | `/api/companies/{id}` | 获取企业详情 |
| GET | `/api/pois` | 按地理范围查询 POI |
| GET | `/api/pois/categories` | 获取 POI 分类列表 |
| GET | `/api/land-use` | 获取土地利用 GeoJSON |
| GET | `/api/health` | 健康检查 |

### 问答请求关键字段（`POST /api/qa/ask[/stream]`）

| 字段 | 说明 |
|------|------|
| `diagram_id` | 关联图纸 ID |
| `question` | 用户问题 |
| `task_hint` | 任务路由提示，决定走 agent / dify / area / industry 哪条链 |
| `shape` | 图纸坐标系下的圈选范围（用于面积计算） |
| `map_bbox` | 地图当前视野 `{west, south, east, north}`（用于企业/POI 空间过滤） |
| `map_selection` | 地图坐标系下的圈选范围（`{type: polygon/circle, ...}`，优先于 bbox） |
| `image_data_url` | 上传图片的 base64 DataURL（走 Dify 视觉分析） |

支持的 `task_hint` 值：

- `计算面积` — area_calculation 工具
- `数据分析问答` — LangGraph Agent 通用工具链
- `规划文本问答` / `图纸+规则综合分析` — Dify 知识库
- `企业关联分析` — industry_relation 工具
- `产业发展方向分析` — industry_direction 工具

## 智能问答工作流

```
用户提问（前端按 chatMode 决定 task_hint）
    │
    ▼
/api/qa/ask[/stream] 路由层
    │
    ├── task_hint=计算面积  ─────────────────► area_calculation 工具 → 直接答复
    │
    ├── task_hint=企业关联分析  ────────────► industry_relation_tool
    │                                            │
    │                                            ▼
    │                                       LLM judgment/report prompt
    │
    ├── task_hint=产业发展方向分析  ─────────► industry_direction_tool
    │                                            │
    │                                            ▼
    │                                       LLM direction prompt（5 段式报告）
    │
    ├── task_hint=规划文本问答 / 图纸+规则  ─► Dify 知识库 chat-messages
    │
    └── task_hint=数据分析问答 / None  ──────► LangGraph Agent
                                                   │
                                                   ▼
                                          意图识别 → 工具链 → 合成答案
```

关键设计：
- **task_hint 优先**：前端显式传 task_hint 时跳过关键词推断，直接走对应分支
- **条件路由**：LangGraph `conditional_edges` 根据 LLM 意图分类决定是否执行工具
- **关键词兜底**：LLM 不可用时通过关键词匹配推断意图（面积/地图/知识库/产业）
- **双层降级**：流式调用失败时降级为阻塞调用，再失败则返回原始工具结果
- **空间范围透传**：`map_bbox` 与 `map_selection` 全链路透传到工具层，selection 优先

## 配置参数

### 图例颜色校准

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `search_radius` | 70.0 | 颜色搜索半径（欧氏距离） |
| `min_pixels` | 30 | 最少匹配像素数 |
| `bucket_size` | 4 | 颜色量化步长 |

### 面积计算

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `tolerance` | 35.0 | 图例颜色匹配容差 |

### 比例尺检测

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 最小线段长度 | 80px | 候选标尺最短像素长度 |
| 最低置信分数 | 3.0 | 候选标尺最低评分 |
| 搜索范围 | 5%-90% | 图像纵向搜索范围 |

### 产业发展方向评分（`industry_direction.py`）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `TOP_N_CHAIN` | 10 | 进入完整评分的候选产业数 |
| `WEIGHTS.industry_base` | 0.20 | 产业基础权重 |
| `WEIGHTS.industry_linkage` | 0.25 | 产业关联度权重 |
| `WEIGHTS.chain_completeness` | 0.25 | 产业链完整度权重 |
| `WEIGHTS.agglomeration` | 0.15 | 集聚度权重 |
| `WEIGHTS.service_support` | 0.15 | 服务配套权重 |
| `SEGMENT_THRESHOLDS` | 见代码 | 各维度归一化的绝对阈值（lo, hi, log?） |
| `FOUNDATION_LEVELS` | 10/5/3/1/0 | 基础分级企业数门槛 |

### 企业关联着色（前端 `RELATION_COLORS`）

| 关系类型 | 颜色 | 含义 |
|---------|------|------|
| `target` | `#ef4444` 红 | 目标产业企业 |
| `upstream` | `#22c55e` 绿 | 上游关联企业 |
| `downstream` | `#f97316` 橙 | 下游关联企业 |
| `other` | `#3b82f6` 蓝 | 其他/默认企业 |

## 开发

### 后端开发

```bash
conda activate Lian
cd backend
uvicorn app.main:app --reload
# API 文档：http://localhost:8000/docs
```

### 前端开发

```bash
cd frontend
npm run dev      # 开发服务器（自动代理 /api → localhost:8000）
npm run build    # 生产构建
npm run preview  # 预览构建结果
```

## License

Private - 仅供内部使用
