# LLM_Lian 技术文档

本文档详细描述规划AI协同平台的系统架构、核心算法、数据模型、API 接口及前端实现。

---

## 目录

1. [系统架构](#1-系统架构)
2. [后端架构详解](#2-后端架构详解)
3. [核心算法](#3-核心算法)
4. [数据模型](#4-数据模型)
5. [API 接口文档](#5-api-接口文档)
6. [前端架构详解](#6-前端架构详解)
7. [LLM 集成](#7-llm-集成)
8. [LangGraph Agent 工作流](#8-langgraph-agent-工作流)
9. [配置参考](#9-配置参考)
10. [部署指南](#10-部署指南)

---

## 1. 系统架构

### 1.1 整体架构

系统采用前后端分离架构，分为四层：

```
┌──────────────────────────────────────────────────────────┐
│                      前端 (React SPA)                     │
│  图纸库面板 │ 工作台（图纸查看+圈选） │ 聊天面板（AI 问答）  │
│            │ 高德地图叠加层             │ 企业抽屉面板       │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTP / SSE
                         ▼
┌──────────────────────────────────────────────────────────┐
│                    API 层 (FastAPI)                       │
│  /api/diagrams  │  /api/qa  │  /api/companies  │ /health │
└────────┬───────────────┬──────────────┬─────────────────┘
         │               │              │
         ▼               ▼              ▼
┌─────────────┐ ┌───────────────┐ ┌──────────────┐
│ 图纸服务     │ │ Agent 服务     │ │ 企业服务      │
│ DiagramSvc  │ │ PlanningAgent │ │ CompanySvc   │
│ LegendSvc   │ │ LLMService    │ │              │
│ ScaleSvc    │ │               │ │              │
└──────┬──────┘ └───────┬───────┘ └──────┬───────┘
       │                │                 │
       ▼                ▼                 ▼
┌─────────────┐ ┌───────────────┐ ┌──────────────┐
│ Tools       │ │ LLM Provider  │ │ companies.db │
│ area_calc   │ │ (GLM/DeepSeek)│ │              │
│ amap (预留) │ │               │ │              │
│ kb   (预留) │ │               │ │              │
└──────┬──────┘ └───────────────┘ └──────────────┘
       │
       ▼
┌──────────────┐
│  app.db      │
│  文件存储     │
│  uploads/    │
│  processed/  │
└──────────────┘
```

### 1.2 双库设计

系统使用两个独立的 SQLite 数据库，实现业务数据与地理数据的物理隔离：

| 数据库 | 文件 | 用途 | Session 工厂 |
|--------|------|------|-------------|
| 主业务库 | `data/app.db` | 图纸元数据、图例、比例尺 | `SessionLocal` |
| 企业库 | `data/companies.db` | 企业地理点位数据 | `CompanySessionLocal` |

双库设计的好处：
- 企业数据可独立备份、替换、批量导入，不影响图纸业务
- 企业数据查询不会阻塞图纸操作
- 便于后续迁移到 PostgreSQL 等数据库

### 1.3 数据流

**图纸处理流程：**

```
用户上传图片
    │
    ▼
[1] 文件保存到 uploads/ 目录
    │
    ▼
[2] 转换为 RGBA PNG 保存到 processed/ 目录
    │
    ▼
[3] 调用视觉 LLM 识别图例 (legend) 和比例尺 (scale)
    │  输入: base64 编码的图片
    │  输出: {legend: {"居住用地": "#FF6600", ...}, scale: {"meters_per_pixel": null, "scale_text": "0 500m 1000m"}}
    │
    ▼
[4] 图例颜色校准 (calibrate_legend_colors)
    │  将 LLM 识别的颜色映射到图纸上实际存在的最接近颜色
    │
    ▼
[5] 比例尺检测 (estimate_scale_from_image)
    │  解析比例尺文字 → 检测水平标尺线段 → 计算 meters_per_pixel
    │
    ▼
[6] 保存 Diagram 记录到数据库
```

**问答流程：**

```
用户提问 + 圈选区域 (shape)
    │
    ▼
[1] 意图识别 (classify_intent)
    │  LLM 判断需要调用的工具: area_calculation / amap / knowledge_base
    │
    ▼
[2] 工具执行 (_run_tools)
    │  ├── area_calculation: 像素级面积统计
    │  ├── amap: 地理数据查询（预留）
    │  └── knowledge_base: 知识检索（预留）
    │
    ▼
[3] 答案合成 (compose_answer)
    │  LLM 基于工具结果生成自然语言回答
    │
    ▼
返回: {answer, intent, tool_results}
```

---

## 2. 后端架构详解

### 2.1 目录职责

| 目录 | 职责 | 关键文件 |
|------|------|----------|
| `core/` | 基础设施：配置、数据库、安全 | `config.py`, `database.py`, `security.py` |
| `models/` | SQLAlchemy ORM 模型 | `diagram.py`, `company.py` |
| `schemas/` | Pydantic 请求/响应模型 | `diagram.py`, `company.py`, `qa.py` |
| `api/` | FastAPI 路由处理 | `diagrams.py`, `companies.py`, `qa.py` |
| `services/` | 业务逻辑层 | `diagram_service.py`, `agent_service.py`, `llm_service.py`, `legend_service.py`, `scale_service.py`, `company_service.py` |
| `tools/` | Agent 可调用工具 | `area_calculation.py`, `amap.py`, `knowledge_base.py` |

### 2.2 依赖关系

```
api/ ──依赖──▶ services/ ──依赖──▶ tools/
                  │                    │
                  ├── models/          └── 无外部依赖（纯算法）
                  ├── schemas/
                  └── core/
```

各层严格遵守单向依赖，`tools/` 不依赖 `services/`，`services/` 不依赖 `api/`。

### 2.3 配置系统

配置通过 `pydantic-settings` 管理（`core/config.py`），支持 `.env` 文件和环境变量：

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Planning AI Platform"
    database_url: str = "sqlite:///./data/app.db"
    company_database_url: str = "sqlite:///./data/companies.db"
    upload_dir: Path = Path("./data/uploads")
    processed_dir: Path = Path("./data/processed")
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_vision_model: str = "deepseek-chat"
    amap_api_key: str = ""
    dify_base_url: str = ""
    dify_api_key: str = ""
    dify_workflow_id: str = ""
    cors_origins: str = "*"
```

使用 `@lru_cache` 缓存 Settings 实例，确保全局单例，同时在首次加载时自动创建上传和处理目录。

---

## 3. 核心算法

### 3.1 图例颜色校准算法 (`legend_service.py`)

**问题**：LLM 视觉模型识别的图例颜色与图纸上实际像素颜色存在偏差，需要校准。

**算法流程**：

```
输入: 图像路径, LLM 识别的图例 {"居住用地": "#FF6600", "商业用地": "#00AA44", ...}

1. 图像预处理
   ├── 读取为 RGB 数组
   ├── 展平为一维像素列表
   └── 颜色量化: 将 RGB 各通道按 bucket_size=4 量化
       例如: (255, 102, 0) → (252, 100, 0)

2. 构建颜色直方图
   ├── 将量化后的 RGB 打包为单一整数: R*4096 + G*64 + B
   ├── 统计每个量化颜色桶的像素数 (np.bincount)
   └── 提取非零桶及其像素计数

3. 逐图例项校准
   对每个 {用地类型: LLM颜色}:
   ├── 计算 LLM 颜色到所有量化颜色的欧氏距离
   ├── 筛选距离 ≤ search_radius (70.0) 的候选颜色
   ├── 若附近像素总数 < min_pixels (30): 保留原色，标记为 not_enough_nearby_pixels
   └── 否则: 选择像素数最多的候选颜色作为校准后颜色

输出: 校准后的图例 {"居住用地": "#FF6600", ...}, 调试信息
```

**关键参数**：

| 参数 | 值 | 作用 |
|------|----|------|
| `search_radius` | 70.0 | 颜色搜索半径（RGB空间欧氏距离），值越大匹配越宽松 |
| `min_pixels` | 30 | 最少匹配像素数阈值，避免匹配到噪声像素 |
| `bucket_size` | 4 | 颜色量化步长，将相近颜色归入同一桶减少计算量 |

**颜色距离计算**：

```python
def _color_distance(left, right):
    diff = left.astype(np.int32) - right.astype(np.int32)
    return np.sqrt(np.sum(diff * diff, axis=-1))
```

使用欧氏距离在 RGB 空间衡量颜色相似度，距离为 0 表示完全一致，最大距离约 441（黑白之间）。

### 3.2 比例尺检测算法 (`scale_service.py`)

**问题**：从规划图纸中自动检测比例尺标尺，计算每像素对应的实际距离。

**算法流程**：

```
输入: 图像路径, LLM 识别的比例尺信息 {"scale_text": "0 500m 1000m", ...}

1. 解析比例尺文字
   ├── 正则匹配: (\d+(?:\.\d+)?)\s*(km|m|米|公里)?
   ├── 单位换算: km/公里 → *1000
   └── 取最大匹配值作为 distance_meters

2. 检测水平暗色线段
   ├── 生成暗色掩码: R<85 & G<85 & B<85
   ├── 在图像 5%-90% 纵向范围内逐行扫描
   ├── 提取连续暗色像素段 (HorizontalRun)
   ├── 过滤: 长度 ≥ 40px 且 ≤ 图像宽度的 35%
   └── 计算线段厚度（中点垂直延伸）
       过滤: 厚度 1-60px

3. 合并重复线段
   └── 按 (y距离≤8, x1距离≤12, x2距离≤12) 去重

4. 多启发式评分 (_score_scale_run)
   对每个候选线段计算综合分数:
   ├── 刻度线得分 (0-12分)
   │   检查线段起点、中点、终点是否存在垂直刻度线
   │   垂直延伸 18-90px 的刻度 +4分/个
   ├── 白色边距得分 (0-1分)
   │   周围区域暗色比例 < 8%
   ├── 上方空白得分 (0-1分)
   │   线段上方 90-220px 区域几乎无暗色
   ├── 长度偏好 (0-1分)
   │   线段长度占图像宽度 4%-18% 时加分
   ├── 长度分数 (0-1分)
   │   min(length/600, 1.0)
   ├── 边框惩罚 (-5分)
   │   线段所在行暗色宽度超过线段1.6倍
   └── 色彩惩罚 (-6分)
       周围区域非白非黑像素 > 12%

5. 选择最佳候选
   ├── 按分数和长度排序
   ├── 过滤: 长度 ≥ 80px, 分数 ≥ 3.0
   └── 计算: meters_per_pixel = distance_meters / pixel_length

输出: 更新后的 scale_json (含 meters_per_pixel)
```

**评分算法的核心思想**：比例尺标尺通常具有以下特征——位于白色/浅色区域、两端有垂直刻度线、上方有空白区域、长度适中、不在图像边框上。评分函数综合这些启发式信号，选出最可能的标尺线段。

### 3.3 用地面积计算算法 (`area_calculation.py`)

**问题**：在图纸上给定一个多边形或圆形区域，计算各用地类型的面积。

**算法流程**：

```
输入: 图像路径, 选区形状, 校准后图例, meters_per_pixel

1. 遍历选区内像素
   ├── 多边形选区: 射线法 (Ray Casting) 判断像素是否在多边形内
   └── 圆形选区: 距离法判断像素是否在圆内

2. 逐像素颜色匹配
   对每个选区内像素 (x, y):
   ├── 读取 RGB 值
   ├── 与所有图例颜色计算欧氏距离
   ├── 选择距离最近的图例颜色
   └── 若距离 ≤ tolerance (35.0): 计入对应用地类型
       否则: 计入未匹配

3. 面积计算
   ├── square_meters_per_pixel = meters_per_pixel²
   ├── 各类型面积 = 像素数 × square_meters_per_pixel
   ├── 公顷 = 平方米 / 10000
   └── 汇总: 匹配面积 / 未匹配面积 / 总面积 / 匹配率

输出: {
  shape, meters_per_pixel, tolerance,
  total_selected_pixels, unmatched_pixels,
  summary: {matched/hectares, unmatched/hectares, total/hectares, matched_ratio},
  areas: {"居住用地": {pixels, square_meters, hectares}, ...}
}
```

**多边形包含检测 - 射线法**：

```python
def point_in_polygon(x, y, points):
    inside = False
    previous = points[-1]
    for current in points:
        xi, yi = current["x"], current["y"]
        xj, yj = previous["x"], previous["y"]
        intersects = (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
        if intersects:
            inside = not inside
        previous = current
    return inside
```

从测试点向右发射水平射线，统计与多边形边的交点数。奇数次交点表示点在多边形内部。

**颜色匹配**：

```python
def nearest_legend_match(rgb, legend, tolerance):
    best_distance = inf
    for land_type, hex_color in legend.items():
        target = hex_to_rgb(hex_color)
        distance = euclidean_distance(rgb, target)
        if distance < best_distance:
            best_distance = distance
            best_type = land_type
    return {
        "land_type": best_type if best_distance <= tolerance else None,
        "matched": best_distance <= tolerance,
        "distance": best_distance,
    }
```

使用欧氏距离衡量像素颜色与图例颜色的相似度，`tolerance` 控制匹配宽松度。值越大匹配率越高但精度越低，推荐范围 25-45。

---

## 4. 数据模型

### 4.1 Diagram（图纸）

```python
class Diagram(Base):
    __tablename__ = "diagrams"

    id: int              # 主键，自增
    filename: str        # 原始文件名
    original_path: str   # 原始文件存储路径
    processed_path: str  # 处理后 PNG 路径（可为空）
    legend_json: str     # 图例 JSON，如 {"居住用地": "#FF6600", "商业用地": "#00AA44"}
    scale_json: str      # 比例尺 JSON，如 {"meters_per_pixel": 2.5, "scale_text": "0 500m 1000m"}
    image_width: int     # 图像宽度（像素）
    image_height: int    # 图像高度（像素）
    created_at: datetime # 创建时间
    updated_at: datetime # 更新时间
```

`legend_json` 详细结构：

```json
{
  "居住用地": "#FF6600",
  "商业用地": "#00AA44",
  "工业用地": "#9933CC",
  "绿地": "#66CC00"
}
```

`scale_json` 详细结构：

```json
{
  "meters_per_pixel": 2.5,
  "scale_text": "0 500m 1000m",
  "source": "estimated_from_scale_bar",
  "scale_detection": {
    "status": "estimated_from_scale_bar",
    "distance_meters": 1000,
    "pixel_length": 400,
    "bbox": {"x1": 100, "y": 800, "x2": 500},
    "score": 8.5,
    "candidates": [...]
  },
  "legend_calibration_status": {
    "enabled": true,
    "items": 5
  },
  "manual_calibration": {
    "enabled": true,
    "meters_per_pixel": 2.5,
    "reference_distance_meters": 500,
    "reference_pixel_length": 200,
    "source": "manual_api"
  }
}
```

### 4.2 Company（企业）

```python
class Company(Base):
    __tablename__ = "companies"
    # 索引: ix_companies_lng_lat (lng, lat) 联合索引

    id: int                    # 主键
    company_name: str          # 公司名称
    status: str                # 经营状态
    legal_representative: str  # 法定代表人
    registered_capital: str    # 注册资本
    paid_in_capital: str       # 实缴资本
    established_at: str        # 成立日期
    district: str              # 所属区县（有索引）
    industry: str              # 所属行业
    company_type: str          # 公司类型
    insured_count: str         # 参保人数
    address: str               # 注册地址
    business_scope: str        # 经营范围
    lng: float                 # 经度（有索引）
    lat: float                 # 纬度（有索引）
    survival_status: str       # 生存状态
```

---

## 5. API 接口文档

### 5.1 图纸管理

#### POST /api/diagrams

上传并处理图纸。

**请求**: `multipart/form-data`，字段 `file` 为图片文件。

**响应**: `DiagramOut`

```json
{
  "id": 1,
  "filename": "规划图.png",
  "original_path": "./data/uploads/abc123.png",
  "processed_path": "./data/processed/abc123.png",
  "legend_json": {"居住用地": "#FF6600"},
  "scale_json": {"meters_per_pixel": 2.5},
  "image_width": 4000,
  "image_height": 3000,
  "created_at": "2025-01-01T00:00:00",
  "updated_at": "2025-01-01T00:00:00"
}
```

**处理过程**：上传 → 图像转换 → LLM 视觉识别 → 图例校准 → 比例尺检测 → 存储。整个流程为异步操作，耗时取决于 LLM 响应速度。

#### GET /api/diagrams

获取图纸列表，按创建时间倒序。

**响应**: `DiagramListOut`

```json
{
  "items": [DiagramOut, ...]
}
```

#### GET /api/diagrams/{id}

获取单个图纸详情。

#### GET /api/diagrams/{id}/image

获取图纸图片文件（优先返回处理后图片）。

**响应**: `FileResponse` (image/png)

#### PATCH /api/diagrams/{id}

重命名图纸。

**请求体**:

```json
{ "filename": "新名称.png" }
```

#### DELETE /api/diagrams/{id}

删除图纸及其关联文件。

#### POST /api/diagrams/{id}/recalibrate-legend

重新校准图例颜色（不重新调用 LLM，仅重新运行颜色校准算法）。

#### POST /api/diagrams/{id}/calibrate-scale

手动校正比例尺。

**请求体**:

```json
{
  "meters_per_pixel": 2.5,
  "reference_distance_meters": 500,
  "reference_pixel_length": 200,
  "scale_text": "0 500m 1000m"
}
```

三种校正方式（提供任一即可）：
- 直接提供 `meters_per_pixel`
- 提供参考距离 + 参考像素长度（系统自动计算 `meters_per_pixel = reference_distance_meters / reference_pixel_length`）
- 附带 `scale_text` 记录比例尺文字

### 5.2 智能问答

#### POST /api/qa/ask

同步问答接口。

**请求体**:

```json
{
  "diagram_id": 1,
  "question": "计算这块区域的各类用地面积",
  "shape": {
    "type": "polygon",
    "points": [{"x": 100, "y": 200}, {"x": 300, "y": 200}, {"x": 300, "y": 400}, {"x": 100, "y": 400}]
  }
}
```

**shape 类型**:
- `"polygon"`: 多边形，需提供 `points` 数组（至少3个点）
- `"circle"`: 圆形，需提供 `center` 和 `radius`

**响应**:

```json
{
  "answer": "选定区域总面积约 12.5 公顷，其中居住用地 8.2 公顷（65.6%），商业用地 3.1 公顷（24.8%）...",
  "intent": {"intent": "area", "tools": ["area_calculation"], "reason": "用户询问用地面积"},
  "tool_results": {
    "area_calculation": {
      "summary": {"total_hectares": 12.5, "matched_ratio": 0.92},
      "areas": {"居住用地": {"pixels": 82000, "square_meters": 82000, "hectares": 8.2}}
    }
  }
}
```

#### POST /api/qa/ask/stream

流式问答接口（Server-Sent Events）。

**请求体**: 与同步接口相同。

**响应**: `text/event-stream`，事件序列如下：

```
data: {"type": "status", "stage": "classify", "message": "正在识别提问意图"}

data: {"type": "intent", "intent": {"tools": ["area_calculation"]}, "message": "已识别工具链：area_calculation"}

data: {"type": "status", "stage": "tools", "message": "正在执行规划分析工具"}

data: {"type": "tool_result", "tool": "area_calculation", "result": {...}, "message": "area_calculation 已完成"}

data: {"type": "tool_results", "tool_results": {...}}

data: {"type": "status", "stage": "answer", "message": "正在组织规划答复"}

data: {"type": "answer_delta", "delta": "选定区域"}

data: {"type": "answer_delta", "delta": "总面积约"}

data: {"type": "final", "answer": "完整回答...", "intent": {...}, "tool_results": {...}}
```

**事件类型**:

| type | 说明 |
|------|------|
| `status` | 阶段状态通知，`stage` 可为 `classify` / `tools` / `answer` |
| `intent` | 意图识别结果 |
| `tool_result` | 单个工具执行结果 |
| `tool_results` | 所有工具执行结果汇总 |
| `answer_delta` | 答案增量文本（流式输出） |
| `final` | 最终完整结果 |
| `error` | 错误信息 |

### 5.3 企业数据

#### GET /api/companies

按地理范围查询企业。

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `min_lng` | float | 是 | 最小经度 |
| `min_lat` | float | 是 | 最小纬度 |
| `max_lng` | float | 是 | 最大经度 |
| `max_lat` | float | 是 | 最大纬度 |
| `limit` | int | 否 | 返回数量上限（默认500，最大2000） |
| `keyword` | string | 否 | 企业名称模糊搜索 |
| `district` | string | 否 | 按区县筛选 |

**响应**:

```json
{
  "items": [{"id": 1, "company_name": "xxx公司", "district": "禅城区", "industry": "制造业", "lng": 113.12, "lat": 23.02, "survival_status": "存续"}],
  "total": 150,
  "truncated": false
}
```

`truncated: true` 表示实际结果超过 limit，已被截断。

#### GET /api/companies/{id}

获取企业详细信息。

### 5.4 健康检查

#### GET /api/health

```json
{"status": "ok", "app": "Planning AI Platform"}
```

---

## 6. 前端架构详解

### 6.1 整体布局

前端采用三栏自适应布局：

```
┌──────────┬─┬───────────────────────┬─┬──────────┐
│          │改│                       │改│          │
│  图纸库   │变│      工作台            │变│  聊天面板 │
│  面板     │条│  (图纸查看+圈选+地图)   │条│          │
│          │  │                       │  │          │
│  - 上传   │  │  - 图片显示            │  │  - 对话   │
│  - 列表   │  │  - 多边形绘制          │  │  - 思考   │
│  - 选择   │  │  - 圆形绘制            │  │  - 结果   │
│          │  │  - 高德地图叠加         │  │          │
│          │  │  - 图例展示            │  │  企业抽屉  │
│          │  │  - 比例尺校准          │  │  (可展开)  │
└──────────┴─┴───────────────────────┴─┴──────────┘
```

使用 CSS Grid 实现，各列宽度可通过拖拽分隔条调整。

### 6.2 核心状态管理

使用 React `useState` 管理全局状态，主要状态分组：

| 状态组 | 变量 | 用途 |
|--------|------|------|
| 图纸状态 | `diagrams`, `selectedId` | 图纸列表与选中图纸 |
| UI 布局 | `libraryCollapsed`, `chatWidth`, `companyDrawerWidth` | 面板折叠与宽度 |
| 绘图状态 | `mode`, `points`, `circle`, `draggingCircle` | 圈选模式与图形数据 |
| 对话状态 | `messages`, `question`, `loading`, `thinkingSteps` | 聊天记录与AI响应 |
| 地图状态 | `showMapLayer`, `companyLayerStatus`, `visibleCompanies` | 地图显示与企业图层 |
| 比例尺 | `scaleCalibrating`, `scaleCalibrationMessage` | 比例尺校准交互 |

### 6.3 绘图交互

**多边形绘制**：
- 点击画布添加顶点，实时连线显示
- 双击或回到起点闭合多边形
- 使用射线法判断鼠标是否靠近起点（闭合提示）

**圆形绘制**：
- 第一次点击设定圆心
- 拖拽设定半径
- 释放鼠标完成绘制

### 6.4 流式响应处理

前端通过 `streamAskDiagram()` 函数处理 SSE 流式响应：

```typescript
// 1. 发起 POST 请求，Accept: text/event-stream
// 2. 使用 ReadableStream API 逐块读取
// 3. 按 \n\n 分割 SSE 事件
// 4. 解析 data: 行的 JSON
// 5. 根据事件类型更新 UI:
//    - status → 更新思考步骤显示
//    - intent → 显示识别到的工具链
//    - tool_result → 显示工具执行结果
//    - answer_delta → 追加到当前回答文本
//    - final → 完成对话轮次
```

### 6.5 高德地图集成

- 地图仅在用户点击地图按钮时加载（懒加载）
- 企业标记在缩放级别 ≥ 13 时显示
- 点击标记弹出信息窗口，显示企业基本信息
- 支持企业详情面板展示

### 6.6 TypeScript 类型定义

```typescript
// 图纸
type Diagram = {
  id: number; filename: string;
  original_path: string; processed_path: string | null;
  legend_json: Record<string, string>;
  scale_json: Record<string, unknown>;
  image_width: number; image_height: number;
  created_at: string; updated_at: string;
};

// 空间选区
type RegionShape =
  | { type: 'polygon'; points: Point[] }
  | { type: 'circle'; center: Point; radius: number };

// 问答响应
type AskResponse = {
  answer: string;
  intent: Record<string, unknown>;
  tool_results: Record<string, unknown>;
};

// SSE 流式事件（7种类型）
type AskStreamEvent =
  | { type: 'status'; stage: 'classify' | 'tools' | 'answer'; message: string }
  | { type: 'intent'; intent: Record<string, unknown>; message: string }
  | { type: 'tool_result'; tool: string; result: Record<string, unknown>; message: string }
  | { type: 'tool_results'; tool_results: Record<string, unknown> }
  | { type: 'answer_delta'; delta: string }
  | { type: 'final'; answer: string; intent: Record<string, unknown>; tool_results: Record<string, unknown> }
  | { type: 'error'; message: string };

// 企业点位 & 详情
type CompanyPoint = { id: number; company_name: string; district: string | null; industry: string | null; lng: number; lat: number; survival_status: string | null; };
type CompanyDetail = { /* 完整企业信息 */ };
```

---

## 7. LLM 集成

### 7.1 LLMService 封装

`LLMService` 封装了与 LLM 提供商的交互，基于 `langchain-openai` 的 `ChatOpenAI`，兼容所有 OpenAI API 格式的提供商。

**三个核心调用**：

| 方法 | 模型 | 用途 | 输入 | 输出 |
|------|------|------|------|------|
| `identify_legend_and_scale` | 视觉模型 | 图纸图例/比例尺识别 | 图片 (base64) | `{legend, scale}` |
| `classify_intent` | 文本模型 | 用户意图识别 | 问题文本 | `{intent, tools, reason}` |
| `synthesize_answer` / `stream_synthesize_answer` | 文本模型 | 答案合成 | 问题 + 工具结果 | 自然语言回答 |

### 7.2 JSON 提取策略

LLM 返回的内容可能包含 Markdown 代码块包裹，`_extract_json()` 方法处理以下格式：

```
```json\n{"key": "value"}\n```     →  提取 JSON
```\n{"key": "value"}\n```         →  提取 JSON
{"key": "value"}                   →  直接解析
前面有文字 {"key": "value"} 后面也有  →  提取第一个 { 到最后一个 }
```

### 7.3 降级策略

- 未配置 `LLM_API_KEY`：视觉识别返回空图例和默认比例尺，意图识别默认调用 `area_calculation`，答案合成直接输出工具结果的 JSON
- LLM 解析失败：返回空图例 + 默认比例尺（meters_per_pixel=1.0），意图识别回退到 `area_calculation`
- 流式输出异常：回退到同步调用，将完整结果作为单次输出

---

## 8. LangGraph Agent 工作流

### 8.1 状态定义

```python
class AgentState(TypedDict, total=False):
    question: str           # 用户问题
    diagram: Diagram        # 关联图纸对象
    shape: dict[str, Any]   # 用户圈选区域
    intent: dict[str, Any]  # 意图识别结果
    tool_results: dict[str, Any]  # 工具执行结果
    answer: str             # 最终答案
```

### 8.2 工作流图

```
          ┌─────────────┐
          │  classify    │  意图识别
          │  (意图识别)   │
          └──────┬──────┘
                 │
                 ▼
          ┌─────────────┐
          │   tools      │  工具执行
          │  (工具调用)   │
          └──────┬──────┘
                 │
                 ▼
          ┌─────────────┐
          │ compose_answer│  答案合成
          │  (答案合成)   │
          └──────┬──────┘
                 │
                 ▼
                END
```

三个节点顺序执行，无条件分支。未来可根据意图类型添加条件路由。

### 8.3 工具调用逻辑

`_run_tools` 节点根据 `intent["tools"]` 列表调用对应工具：

| 工具 | 触发条件 | 实现 |
|------|----------|------|
| `area_calculation` | 默认执行（无 tools 时自动添加） | 像素级颜色匹配面积计算 |
| `amap` | 意图涉及地理位置/路线/周边 | 预留接口，返回 reserved 状态 |
| `knowledge_base` | 意图涉及规范/政策/历史资料 | 预留接口，返回 reserved 状态 |

**面积计算前置检查**：若图例为空，跳过计算并返回 `missing_legend` 状态提示。

### 8.4 流式输出

`ask_stream` 方法将工作流各阶段状态通过异步生成器实时推送：

```python
async def ask_stream(self, db, diagram_id, question, shape):
    # 1. 意图识别阶段
    yield {"type": "status", "stage": "classify", ...}
    state = await self._classify(state)
    yield {"type": "intent", "intent": ..., ...}

    # 2. 工具执行阶段
    yield {"type": "status", "stage": "tools", ...}
    state = await self._run_tools(state)
    for tool, result in tool_results.items():
        yield {"type": "tool_result", "tool": tool, ...}
    yield {"type": "tool_results", ...}

    # 3. 答案合成阶段（流式输出）
    yield {"type": "status", "stage": "answer", ...}
    async for delta in self.llm.stream_synthesize_answer(...):
        yield {"type": "answer_delta", "delta": delta}
    yield {"type": "final", "answer": ..., ...}
```

---

## 9. 配置参考

### 9.1 环境变量完整列表

| 变量 | 默认值 | 必填 | 说明 |
|------|--------|------|------|
| `APP_NAME` | `Planning AI Platform` | 否 | 应用名称 |
| `APP_ENV` | `dev` | 否 | 运行环境 |
| `DATABASE_URL` | `sqlite:///./data/app.db` | 否 | 主业务数据库 URL |
| `COMPANY_DATABASE_URL` | `sqlite:///./data/companies.db` | 否 | 企业数据库 URL |
| `UPLOAD_DIR` | `./data/uploads` | 否 | 上传文件存储目录 |
| `PROCESSED_DIR` | `./data/processed` | 否 | 处理后文件存储目录 |
| `LLM_BASE_URL` | `https://api.deepseek.com` | 是 | LLM API 基础 URL |
| `LLM_API_KEY` | (空) | 是 | LLM API 密钥 |
| `LLM_MODEL` | `deepseek-chat` | 否 | 文本模型名称 |
| `LLM_VISION_MODEL` | `deepseek-chat` | 否 | 视觉模型名称 |
| `AMAP_API_KEY` | (空) | 否 | 高德地图 JS API Key |
| `DIFY_BASE_URL` | (空) | 否 | Dify 平台 URL（预留） |
| `DIFY_API_KEY` | (空) | 否 | Dify API Key（预留） |
| `DIFY_WORKFLOW_ID` | (空) | 否 | Dify 工作流 ID（预留） |
| `CORS_ORIGINS` | `*` | 否 | CORS 允许的源（逗号分隔，`*` 允许全部） |

### 9.2 Vite 开发代理

```typescript
// vite.config.ts
server: {
  port: 5173,
  proxy: {
    '/api': 'http://127.0.0.1:8000',
  },
}
```

前端开发时，所有 `/api` 请求自动代理到后端。

---

## 10. 部署指南

### 10.1 开发环境

```bash
# 终端 1: 后端
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 终端 2: 前端
cd frontend
npm run dev
```

### 10.2 生产部署

**后端**：

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

推荐使用 Nginx 反向代理，配置示例：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # SSE 支持
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }

    location / {
        root /path/to/LLM_Lian/frontend/dist;
        try_files $uri $uri/ /index.html;
    }
}
```

**前端**：

```bash
cd frontend
npm run build
# 产物在 dist/ 目录，部署到 Nginx 静态文件目录
```

### 10.3 数据迁移

企业数据通过脚本导入：

```bash
cd backend
python -m scripts.init_companies
```

脚本从 `企业数据/佛山市企业.csv` 读取数据，按 5000 条一批批量插入 `companies.db`。重复执行时检测已有数据，不会重复导入。

### 10.4 注意事项

1. **SQLite 限制**：SQLite 不支持并发写入，生产环境建议迁移到 PostgreSQL。需修改 `DATABASE_URL` 和 `COMPANY_DATABASE_URL`，并移除 `connect_args={"check_same_thread": False}`。
2. **文件存储**：当前使用本地文件系统存储上传的图纸，生产环境建议使用对象存储（如 S3/MinIO）。
3. **LLM API Key 安全**：`.env` 文件不要提交到版本控制，生产环境使用环境变量或密钥管理服务。
4. **SSE 超时**：Nginx 默认 60 秒超时会中断流式响应，需要设置 `proxy_read_timeout` 为更大值。
5. **企业数据更新**：更新企业数据时需删除 `data/companies.db` 后重新执行导入脚本。
