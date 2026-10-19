# VisionDoctor 实施状态

> 最后更新：2026-10-17（Asia/Shanghai）
> 本文件只记录已观察到的事实。计划中的目录或能力不视为已经实现。

## 1. 仓库基线

- 检查入口目录：`D:\比赛作品\作品1`。
- 阶段交付根目录：`D:\比赛作品\作品1\阶段0`；检查时该目录已存在且为空。
- Git 初始基线：入口目录及其父级未发现 `.git`，`git rev-parse --show-toplevel` 返回“not a git repository”。阶段 0 首次检查时无法验证分支、跟踪状态或差异。
- Git 当前状态：用户随后在 `D:\比赛作品\作品1\阶段0` 执行 `git init -b main`，该目录现为分支 `main` 上的空 Git 仓库；没有提交或远程推送。用户执行 `git add -N` 将三个阶段文件标记为 intent-to-add，以便在未暂存内容的情况下执行 diff 检查。
- 初始文件：除空目录 `阶段0/` 外，入口目录内未发现文件或其他目录。
- 项目说明：在当前目录向上检查 `AGENTS.md`、`README.md`、`CONTRIBUTING.md`、`PROJECT.md`、`CLAUDE.md`，未发现适用文件。
- VisionDoctor 代码：未发现；本阶段未创建业务代码。
- Python：`Python 3.11.7`（`D:\haunjing\python.exe`）。`py --version` 报告未安装可供 Python Launcher 使用的 Python。
- 可用 Python 工具（通过 `python -m` 实际验证）：pytest 7.4.0、Black 23.11.0、mypy 1.8.0、isort 5.9.3、Flake8 6.0.0、Pylint 2.16.2、pip 23.3.1。ruff、pre-commit、uv、Poetry 未发现。
- 相关运行库探查：Streamlit 1.30.0、FastAPI 0.127.1、Pydantic 2.12.5、Pillow 12.0.0、NumPy 1.26.4、pandas 3.0.2、scikit-image 0.22.0 和 SQLAlchemy 2.0.25 已安装；OpenCV、ImageHash、OpenAI、Anthropic、psycopg/psycopg2、redis、pymongo、MySQL Connector/Python 未发现。此项仅说明当前解释器环境，不构成项目依赖声明或兼容性验证。
- API Key/凭证：按环境变量名称检查，未发现匹配 `API_KEY`、`SECRET`、`TOKEN`、`PASSWORD`、常见数据库或云服务命名的变量；未读取或显示任何变量值。项目目录内也未发现 `.env`、凭证或密钥命名的配置文件。这不证明系统其他位置不存在凭证。
- 数据库/外部服务：发现 MySQL 8.0.45 客户端和 Ollama 0.34.4 客户端；未发现相关运行进程，Ollama 客户端明确无法连接运行实例。PostgreSQL、Redis 和 MongoDB 命令未发现。Windows Service Control Manager 拒绝访问，因此不能确认是否安装或运行了系统服务。未尝试连接数据库或外部网络服务。

## 2. 当前阶段

**阶段 9：Complete**

本地交付验收已完成：确定性 Demo 可生成，Smoke Test、94 项自动化测试、全仓 Ruff、compileall 和 Git whitespace 检查均通过；Streamlit 服务实际返回 HTTP 200 后已停止。README 已与真实命令、范围、安全边界和部署前步骤对齐。仓库仍没有提交、远程地址或线上部署，因此“本地代码可进入提交步骤”不等于已有可提交的 GitHub 仓库 URL 或 Demo URL。

## 3. 阶段状态

| 阶段 | 范围 | 状态 | 备注 |
|---|---|---|---|
| 阶段 0 | 仓库基线与项目契约 | Complete | 契约、状态记录与保守忽略规则已完成；Git 验证通过。 |
| 阶段 1 | 项目骨架、配置与核心 schema | Complete | src layout、集中配置、核心 Pydantic v2 模型、最小入口和测试已通过验收。 |
| 阶段 2 | 安全解压与 YOLO Detection 解析 | Complete | ZIP 安全边界、两类 YOLO 目录布局和容错标签解析已通过测试。 |
| 阶段 3 | 标注异常检查器 | Complete | 9 类标注 Issue、稳定 ID、定位证据和可配置极小框阈值已通过测试。 |
| 阶段 4 | 图片质量、重复检测与类别分布 | Complete | 独立检查器及 Parser→`IMAGE_UNREADABLE` 真实链路均已通过测试。 |
| 阶段 5 | Health Score、完整 Pipeline 与 Demo 数据 | Complete | 五类封顶扣分、ZIP 到 AuditReport 编排和确定性 Demo/Smoke Test 已通过。 |
| 阶段 6 | Dataset Doctor、结构化输出与 Fallback | Complete | 单 Agent、最小化 Prompt、schema 校验、fake LLM 和无 Key fallback 已通过。 |
| 阶段 7 | JSON 与 HTML 报告 | Complete | JSON round-trip、HTML 安全转义、三种 diagnosis 状态及完整回归已通过。 |
| 阶段 8 | Streamlit Demo 与端到端集成 | Complete | 四标签页面、临时上传、Dashboard、Issue Explorer、Doctor 和报告下载已验证。 |
| 阶段 9 | README、全量质量检查与交付验收 | Complete | 本地质量门禁全部通过；外部 GitHub 推送和 Streamlit Cloud 部署留给用户执行。 |

## 4. 实际修改文件

- `docs/MVP_SPEC.md`：新建项目契约。
- `docs/IMPLEMENTATION_STATUS.md`：新建基线与阶段状态记录。
- `.gitignore`：新建保守的 Python 临时文件、密钥、本地上传数据和派生报告忽略规则。

未修改应用代码、测试、依赖清单或 Git 历史。

## 5. 实际执行命令及结果

### 5.1 基线检查

| 命令/检查 | 真实结果摘要 |
|---|---|
| `(Get-Location).Path` | `D:\比赛作品\作品1` |
| `git branch --show-current` | 失败：不是 Git 仓库。 |
| `git status --short`（修改前） | 失败：不是 Git 仓库。 |
| `rg --files` 与 `Get-ChildItem -Force -Recurse` | 初始仅发现空目录 `D:\比赛作品\作品1\阶段0`。 |
| `git rev-parse --show-toplevel` 与父级 `.git` 检查 | 失败/未发现：当前目录及父级没有 Git 元数据。 |
| 项目说明文件检查 | 未发现适用的 `AGENTS.md` 或其他列出的说明文件。 |
| `python --version` | 成功：Python 3.11.7。 |
| `py --version` | 失败：Python Launcher 未找到已安装 Python。 |
| `python -m <tool> --version` | 成功验证 pytest、Black、mypy、isort、Flake8、Pylint、pip；版本见仓库基线。 |
| 敏感环境名称与配置文件名检查 | 未发现匹配项；没有读取或输出值。 |
| 常见数据库/外部服务命令、进程、服务检查 | 发现 MySQL/Ollama 客户端；未发现相关进程；服务查询因权限被拒绝。 |

### 5.2 用户指定命令的首次执行

| 命令 | 结果 |
|---|---|
| `git status --short` | 已执行，退出码 128：`fatal: not a git repository (or any of the parent directories): .git`。 |
| `git diff --check` | 已执行，退出码 129：警告当前不是 Git 仓库并显示 `git diff --no-index` 用法；未产生可用于验收的 whitespace diff 结果。 |
| `git diff -- docs/MVP_SPEC.md docs/IMPLEMENTATION_STATUS.md .gitignore` | 已执行，退出码 129：当前不是 Git 仓库，限定 pathspec 的比较无法进行；未产生 diff。 |

上述结果记录的是 Git 初始化前的真实基线，不代表当前仓库状态。用户随后实际执行：

- `git init -b main`：成功，在阶段交付根目录建立空仓库和 `main` 分支。
- `git status --short`：显示 `.gitignore` 与 `docs/` 为未跟踪内容。
- `git add -N -- .gitignore docs/MVP_SPEC.md docs/IMPLEMENTATION_STATUS.md`：成功，将三个文件标记为 intent-to-add；未正式暂存、提交或推送。
- 初始化后的首次 `git diff --check`：退出码 2，发现 `docs/IMPLEMENTATION_STATUS.md` 和 `docs/MVP_SPEC.md` 文件末尾各有一个多余空行；本次修复正在移除这两个空行。

### 5.3 Git 初始化后的最终验证

| 命令 | 结果 |
|---|---|
| `git status --short` | 退出码 0；仅显示 `.gitignore`、`docs/IMPLEMENTATION_STATUS.md`、`docs/MVP_SPEC.md` 三个 intent-to-add 新文件。 |
| `git diff --check` | 退出码 0；没有 whitespace 错误。Git 报告 LF 将来可能转换为 CRLF 的 Windows 行尾提示，该提示不影响退出码或本阶段验收。 |
| `git diff -- docs/MVP_SPEC.md docs/IMPLEMENTATION_STATUS.md .gitignore` | 退出码 0；正常展示且仅展示三个允许文件的新增差异。 |

### 5.4 非 Git 补充检查

这些检查只补充文件范围和文本质量证据，不替代用户指定的 Git 命令：

| 检查 | 结果 |
|---|---|
| 递归列出阶段交付根目录内的文件并与白名单比较 | 通过：恰好存在 `.gitignore`、`docs/MVP_SPEC.md`、`docs/IMPLEMENTATION_STATUS.md` 三个文件。 |
| 检查两个文档的必需主题/章节标题 | 通过：未发现缺失主题。 |
| 检查三个文件的尾随空白和 Git 冲突标记 | 通过：未发现。 |

## 6. 未验证事项

- 阶段 0 当时没有业务代码或业务测试；阶段 1 与阶段 2 的实际测试结果分别记录在第 10、11 节。
- 图片质量、重复图片、类别分布、Health Score、ZIP→AuditReport Pipeline、deterministic/模拟 LLM 诊断、JSON/HTML 报告及 Streamlit UI 集成已有自动化测试。真实 LLM API 和真实浏览器文件选择/下载点击仍未验证。
- 未查询网络、调用外部 API、连接数据库或向 LLM 发送数据。
- Windows 服务状态因权限不足而未验证。
- 未全面扫描项目目录之外的凭证或配置；因此只能报告本次检查范围内未发现。

## 7. 已知限制

- 当前是尚无首个提交的空 Git 仓库；阶段 0 至阶段 6 文件均为 intent-to-add，未正式暂存、提交或推送。
- 已创建依赖清单，但尚未在全新隔离环境中执行完整依赖安装；本阶段仅按需安装并验证了 Ruff 0.17.1。
- 阶段划分是后续实施跟踪框架，不代表时间承诺，也不代表任何后续功能已经开始。
- 当前 `.gitignore` 仅覆盖明确的本地临时/敏感产物；没有使用会普遍隐藏 ZIP、图片、标签或测试夹具的宽泛规则。

## 8. 下一阶段开始前必须重新验证

1. 重新确认 Git 仓库根目录和分支，并执行 `git status --short`、`git diff --check` 和限定路径 diff。
2. 重新读取仓库根及目标子目录适用的全部 `AGENTS.md`/项目说明。
3. 重新列出文件，确认没有新的用户修改，并区分本阶段文档与用户文件。
4. 确认 Python 解释器、依赖管理方式和实际可调用的测试/格式化工具。
5. 确认 `.gitignore` 与计划采用的上传、临时目录和测试夹具布局不冲突。
6. 保持“无 API Key 完整运行”、不使用数据库、不改原始标签、不训练模型等契约不变；任何范围变更须先更新本契约和状态记录。

## 9. 阶段 0 验收判断

- 两个文档存在，范围、约束和阶段状态一致：满足。
- 当前可观察目录状态已真实记录：满足。
- 未修改或创建业务代码、测试或依赖清单：满足。
- 未声称不存在的测试、数据库或 API 已验证：满足。
- `.gitignore` 只包含保守的临时文件、密钥和本地上传/派生报告目录规则，没有全局忽略 ZIP、图片、标签或测试数据：满足。
- 用户指定的三条 Git 命令均已在最终修复后成功执行并返回退出码 0：满足。

因此，阶段 0 **满足全部验收标准**，状态为 **Complete**。该结论是阶段 1 开始前复核的有效基线。

## 10. 阶段 1 实施记录

### 10.1 开始前实时复核

- Git 根目录为 `D:\比赛作品\作品1\阶段0`，分支为 `main`。
- 阶段 0 的 `.gitignore`、`docs/MVP_SPEC.md`、`docs/IMPLEMENTATION_STATUS.md` 均真实存在。
- `docs/IMPLEMENTATION_STATUS.md` 将阶段 0 标记为 `Complete`，与项目契约及实时文件树一致。
- 开始前 `git diff --check` 退出码为 0；阶段 0 的限定路径 diff 可正常生成。
- 未发现适用的 `AGENTS.md`，也未发现既有 Python 文件或依赖清单。

### 10.2 实际变更

- 新建 `app.py`：仅提供可导入的 `main()` 和 Streamlit 占位页，不包含完整界面。
- 新建 `requirements.txt`：声明运行依赖，明确使用 `opencv-python-headless`，未引入数据库驱动或数据库服务。
- 新建 `requirements-dev.txt`：引用运行依赖并声明 pytest 与 Ruff。
- 新建 `.env.example`：仅包含禁用 LLM 的默认值和明显占位符，不含真实凭证。
- 补充 `.gitignore`：增加构建、覆盖率及测试缓存等明确的本地产物规则。
- 新建 `src/vision_doctor/__init__.py`、`config.py`、`models.py`，以及 `checks`、`diagnosis`、`ingest`、`parsers`、`reports`、`ui` 的空包入口。
- 新建 `tests/conftest.py`、`tests/test_config.py`、`tests/test_models.py`。
- 更新本状态文件；未修改 `docs/MVP_SPEC.md`，未实现解析器、检查器、Agent、报告生成或完整 UI。

### 10.3 实际测试结果

| 命令 | 结果 |
|---|---|
| `python --version` | 通过：Python 3.11.7，满足 Python 3.10+ 要求。 |
| `python -m pytest -q tests/test_config.py tests/test_models.py` | 通过：9 passed。 |
| `python -m ruff check app.py src/vision_doctor tests/test_config.py tests/test_models.py` | 首次失败：当前解释器没有 Ruff；安装 Ruff 0.17.1 后复测通过：`All checks passed!`。 |
| `python -m compileall app.py src/vision_doctor` | 通过：入口和全部包模块成功编译。 |
| `git diff --check` | 对全部新增文件执行 `git add -N` 后通过，退出码 0；只有 Windows LF/CRLF 转换提示。 |
| `git status --short` | 通过：仅显示阶段 0 与阶段 1 允许文件为 intent-to-add，没有额外业务文件。 |

没有跳过必需命令。没有运行解析、图片检查、重复检测、评分、诊断或报告测试，因为这些能力明确不属于阶段 1。

### 10.4 数据模型的重要决定

- 所有对象型契约继承统一 `ContractModel`：拒绝未知字段、剥离字符串首尾空白并启用赋值校验。
- `Severity` 是值为 `info`、`warning`、`error`、`critical` 的字符串枚举；其他值由 Pydantic 拒绝。
- `BoundingBox` 是长度固定为 4 的 RootModel，顺序为 YOLO 的 `x_center, y_center, width, height`；要求有限数值、归一化正尺寸且整个框不越出图片边界。
- 分数统一限制在 `[0, 100]`；分项权重限制在 `(0, 1]`。Health Score 明确携带方法版本和免责声明。
- `Issue.evidence` 只接受 JSON 可序列化值；Issue ID 可由检查器提供稳定值，也有 UUID 默认值。
- `Diagnosis` 为 deterministic 与 LLM 路径使用同一结构，二者只能引用已有 Issue ID。
- `AuditReport.schema_version` 固定为 `1.0.0`，时间戳必须带时区，所有输出可通过 `model_dump(mode="json")` 序列化。
- 配置使用 `VISION_DOCTOR_` 前缀和双下划线嵌套覆盖，例如 `VISION_DOCTOR_UPLOAD__MAX_ARCHIVE_SIZE_MB`；LLM 默认禁用且 API Key 默认为空。

### 10.5 阶段 2 可依赖的真实接口

- `vision_doctor.config.Settings`：包含 `upload`、`image_quality`、`duplicate_detection`、`llm` 四组已验证配置。
- `vision_doctor.config.get_settings()`：提供进程内缓存的验证后配置实例；测试需要改变环境时可直接构造 `Settings(_env_file=None)`。
- `vision_doctor.models` 以及包顶层导出的 15 个核心契约：`Severity`、`BoundingBox`、`AnnotationRecord`、`ImageRecord`、`DatasetSummary`、`DatasetManifest`、`Issue`、`DuplicateGroup`、`DistributionStats`、`ScoreBreakdown`、`HealthScore`、`PriorityFinding`、`RecommendedAction`、`Diagnosis`、`AuditReport`。
- 模型支持 Pydantic v2 的 `model_validate()`、`model_dump()` 和 `model_dump_json()`；阶段 2 应复用这些契约，不另建不兼容的数据字典。
- `vision_doctor.ingest` 与 `vision_doctor.parsers` 当前仅为空包边界，不包含可调用实现。

### 10.6 未验证事项与限制

- 未在 Python 3.10 解释器上直接运行；实现避免使用 Python 3.11 专属 `datetime.UTC`，但 3.10 兼容性仍需在相应解释器或 CI 中验证。
- 未在全新虚拟环境中执行 `pip install -r requirements.txt`；依赖可解析性和 Streamlit/OpenCV 的联合运行留待后续环境验证。
- `DatasetSummary` 与 `DatasetManifest` 的跨字段计数一致性尚未强制校验，由阶段 2 解析流程负责生成并测试一致结果。
- 当前模型是结构契约，不代表任何数据集解析、异常检测、评分、诊断或报告功能已经实现。

阶段 1 的所有必需验收项均已满足，状态为 **Complete**。该结论构成阶段 2 开始前的有效基线。

## 11. 阶段 2 实施记录

### 11.1 开始前实时复核

- Git 根目录仍为 `D:\比赛作品\作品1\阶段0`，分支为 `main`；开始前只有阶段 0 和阶段 1 的 intent-to-add 文件。
- 未发现适用的 `AGENTS.md`；所有必读文档、依赖、配置、模型和阶段 1 测试均真实存在并已重新读取。
- `python -m pytest -q tests/test_config.py tests/test_models.py` 在修改前通过：9 passed。
- 阶段 1 状态为 `Complete`，文档与实时文件树未发现矛盾。

### 11.2 实际变更

- 新建 `src/vision_doctor/archive.py`：提供 ZIP 内容识别、中央目录预检、路径规范化、软链接/特殊文件拒绝、加密条目拒绝、文件数量/单文件/总解压量/压缩比限制，以及逐块安全写入随机临时目录。
- 新建 `src/vision_doctor/parser.py`：解析根目录 `data.yaml`、递归发现 `images/` 与 `labels/`、读取图片元数据、按相对 stem 配对并容错解析 YOLO Detection 标签。
- 兼容修改 `config.py`：图片扩展名白名单明确为 BMP、JPEG、JPG、PNG、WEBP。
- 兼容修改 `models.py`：新增 `ParseErrorRecord`，并为 `DatasetManifest` 增加默认空的 `parse_errors` 字段；阶段 1 构造方式保持兼容。
- 新建 `tests/test_archive.py` 和 `tests/test_parser.py`；未修改 `tests/conftest.py`。
- 更新本状态文件；未修改应用入口、依赖清单、阶段 1 测试或其他业务模块。

### 11.3 ZIP 安全行为

- 输入必须是存在的普通文件且内容可由 `zipfile.is_zipfile` 识别；损坏或无法读取时抛出可读的 `InvalidArchiveError`。
- 拒绝 POSIX/Windows 绝对路径、盘符路径、`..` 穿越、歧义路径、重复目标路径、软链接、非普通特殊文件和加密条目。
- `UploadLimits` 控制上传 ZIP 大小、普通文件数量、单文件解压大小、总解压大小和逐文件压缩比。
- 全部条目在写入前完成中央目录校验；实际解压时再次校验目标仍位于随机目录内，并逐块核对真实写入量。
- `extract_zip_safely()` 返回 `ExtractedArchive` 上下文管理器；调用方必须使用 `with` 或显式 `cleanup()`。上下文退出及提取异常都会清理随机临时目录。
- 解压逻辑只读取字节并写入普通文件，从不导入、调用或执行压缩包内容。

### 11.4 已支持的 YOLO 目录与解析行为

- 支持根目录含 `data.yaml`、`images/*`、`labels/*` 的平铺形式。
- 支持 `images/train/*`、`images/val/*`、`labels/train/*`、`labels/val/*`，并可按同一规则处理更深的对应子目录。
- `names` 支持非空字符串列表，以及从 0 开始连续的非负整数键字典。
- 支持 `.jpg`、`.jpeg`、`.png`、`.bmp`、`.webp`，扩展名匹配不区分大小写。
- 图片与标签按各自目录下的相对路径去扩展名后匹配，而不是只按文件名匹配；报告路径统一使用相对于数据集根目录的 POSIX 形式。
- 合法行解析为 `AnnotationRecord`；空行忽略。字段数量、数值、未知类别、bbox 和 UTF-8 编码错误记录为 `ParseErrorRecord`，不终止其他行或图片的解析。
- 无标签图片保留为零标注 `ImageRecord`；无匹配图片的标签记录 `label.orphan`。
- 缺失/无效 `data.yaml`、不支持的 `names`、缺失 `images/` 或 `labels/`、没有受支持图片或相对键冲突属于数据集级错误。图片无法解码时保留到 `unreadable_image_paths` 并继续解析，供图片质量检查器生成 Issue。

### 11.5 实际测试结果

| 命令 | 结果 |
|---|---|
| `python -m pytest -q tests/test_config.py tests/test_models.py` | 修改前和修改后均通过：9 passed。 |
| `python -m pytest -q tests/test_archive.py tests/test_parser.py` | 通过：19 passed。 |
| `python -m ruff check src/vision_doctor/archive.py src/vision_doctor/parser.py tests/test_archive.py tests/test_parser.py` | 首次发现 3 个代码质量问题；修复后复测通过：`All checks passed!`。 |
| `python -m compileall src/vision_doctor` | 通过：全部模块成功编译。 |
| `git diff --check` | 对新增文件执行 `git add -N` 后通过，退出码 0；只有 Windows LF/CRLF 转换提示。 |
| `git status --short` | 通过：仅显示阶段 0 至阶段 2 的允许文件为 intent-to-add。 |
| `python -m pytest -q`（补充全量回归） | 通过：28 passed。 |
| `python -m ruff check src/vision_doctor/config.py src/vision_doctor/models.py tests/conftest.py`（补充检查） | 通过：`All checks passed!`。 |

没有跳过必需命令。阶段 2 测试没有连接网络、数据库或外部服务。

### 11.6 解析限制与阶段 3 可依赖接口

- 数据集必须已经安全解压，且 `data.yaml` 必须直接位于传给 `parse_yolo_dataset()` 的根目录；当前不自动剥离 ZIP 顶层包装目录。
- Parser 扫描实际 `images/` 与 `labels/` 树，不解释 `data.yaml` 中的 `train`、`val`、远程 URL 或外部路径字段。
- `names` 整数键必须从 0 连续；字符串数字键、稀疏键、COCO、分割和姿态格式不支持。
- Parser 为构建 `ImageRecord` 会完整解码图片、读取尺寸并计算 SHA-256；无法解码的图片不创建虚假的尺寸记录，而是保留相对路径供图片质量检查器处理。
- `extract_zip_safely(path, limits=..., temp_root=...)` 是不受信 ZIP 的唯一入口；返回值必须被清理。
- `parse_yolo_dataset(root, source_archive=..., upload_limits=...)` 返回含合法记录和 `parse_errors` 的 `DatasetManifest`。
- 阶段 3 可以直接消费 `manifest.images`、`manifest.annotations`、`manifest.class_names`、`manifest.parse_errors` 与一致的 `manifest.summary`；不得重新解析坏标签或修改源文件。

阶段 2 的所有必需验收项均已满足，状态为 **Complete**。该结论构成阶段 3 开始前的有效基线。

## 12. 阶段 3 实施记录

### 12.1 开始前实时复核

- Git 根目录仍为 `D:\比赛作品\作品1\阶段0`，分支为 `main`；开始前当前 diff 包含 23 个阶段 0 至阶段 2 的 intent-to-add 文件，共 1838 行新增内容。
- 已重新读取 `docs/MVP_SPEC.md`、本状态文件、`models.py`、`parser.py`、`tests/test_parser.py` 和当前差异范围；未发现适用的 `AGENTS.md`。
- `python -m pytest -q tests/test_archive.py tests/test_parser.py` 在修改前通过：19 passed。
- 开始前 `git diff --check` 退出码 0；阶段 2 状态与实时实现没有发现矛盾。

### 12.2 实际变更

- 新建 `src/vision_doctor/checkers/__init__.py` 和 `checkers/annotation.py`，提供不依赖 Streamlit 或文件系统的纯 `check_annotations()` 业务逻辑。
- 新建 `tests/test_annotation_checker.py`，覆盖全部 9 个必需 Issue code、正常样本、坏文件隔离、稳定 ID 和阈值覆盖。
- 兼容修改 `models.py`：`ImageRecord` 增加 `label_path`/`label_status`；`ParseErrorRecord` 增加 class、原始 bbox 和 metrics；`Issue` 增加显式 bbox、metrics 与 suggested action。新增字段均有兼容默认值。
- 兼容修改 `parser.py`：保留 missing/empty/present 标签状态，并将 class、非数字/非有限值、非正尺寸、基础范围和跨边界错误分别结构化记录。
- 扩充 `tests/test_parser.py`，验证标签状态以及非数字、NaN、Inf、非正尺寸、越界和跨边界分类。
- 更新本状态文件；未修改 `tests/conftest.py`，也未修改允许范围之外的应用、依赖、配置、归档或其他模块。

### 12.3 Issue 证据契约与去重

- 每个检查器 Issue 都显式包含稳定 `issue_id`、code、severity、message、相对路径、可选标签行、可选原始 bbox、metrics、suggested action 和兼容的 evidence 聚合字段。
- ID 由 code、相对路径、行号和 bbox 的规范 JSON 经 SHA-256 截断生成；相同 manifest 与配置重复检查会产生相同 ID。
- 检查器按稳定顺序处理图片标签状态、Parser 错误和合法小框，并按稳定 ID 去重；同一标签行只由 Parser 生成一个首要结构错误，不会同时报告无意义的范围/边界重复错误。
- `LABEL_EMPTY` 为 `Severity.INFO`，消息明确说明其可能是有意的负样本，不描述为确定错误。
- 没有自然行号或 bbox 的文件级 Issue 使用 `None`，字段仍完整存在；行级与 bbox 级 Issue 的定位值均非空。

### 12.4 各 Issue code 的实际测试证据

| Issue code | 测试输入与已验证证据 |
|---|---|
| `LABEL_MISSING` | `images/missing.jpg` 无匹配标签；生成期望 `labels/missing.txt` 路径、图片 ID、warning 和核实负样本建议。 |
| `LABEL_ORPHAN` | `labels/orphan.txt` 无对应图片；生成该相对路径、warning 和配对/移除建议。 |
| `LABEL_EMPTY` | 标签仅含空白；生成 info，消息包含“may be an intentional negative sample”，不将其断言为错误。 |
| `LABEL_PARSE_ERROR` | 四列错误行生成带 `annotation_line=1` 的 Issue；Parser 测试另验证普通非数字、`NaN`、`Inf` 均归入结构化解析错误。 |
| `CLASS_ID_INVALID` | 未在 `data.yaml` 声明的 class 9 生成 error；Parser 测试另验证非整数 class token。 |
| `BBOX_NON_POSITIVE` | width 为 0 的行生成 error，保留原始 bbox、行号及 width/height metrics。 |
| `BBOX_OUT_OF_RANGE` | `x_center=1.2` 生成 error，独立于像素边界换算，保留归一化 metrics。 |
| `BBOX_CROSSES_BORDER` | `x_center=0.05,width=0.2` 的基础值均在范围内，但换算 left 小于 0；生成独立 error 和四边 metrics。 |
| `BBOX_TINY` | 100×100 图片中 0.005 宽高框换算为 0.5×0.5 像素；生成 warning、像素 metrics 和阈值 metrics。 |

正常 0.2×0.2 标签不产生 Issue。包含坏行的图片与另一张 tiny-box 图片同时解析时，两类 Issue 均被发现，证明单个损坏标签文件不会阻止其他图片检查。

### 12.5 阈值配置与接口

- `AnnotationCheckConfig` 是不可变配置对象，默认最小宽/高为 2 像素、最小面积为 16 平方像素；所有值必须非负。
- `check_annotations(manifest, config=...)` 从传入配置读取阈值。测试将阈值覆盖为 6 像素/36 平方像素后，默认正常的 5×5 像素框被正确标记为 `BBOX_TINY`。
- 本阶段白名单不允许修改 `config.py`，因此该配置尚未并入环境变量驱动的全局 `Settings`；调用方应显式传入，后续如需全局覆盖必须在相应阶段授权修改配置文件。
- 检查器只消费 `DatasetManifest`，不打开、修改或重新解析源图片/标签。

### 12.6 实际测试结果

| 命令 | 结果 |
|---|---|
| `python -m pytest -q tests/test_archive.py tests/test_parser.py`（开始前） | 通过：19 passed。 |
| `python -m pytest -q tests/test_parser.py tests/test_annotation_checker.py` | 首次因 `parser.py` 遗漏 `math` 导入而 8 failed、7 passed；在允许范围内修复后通过：15 passed。 |
| `python -m pytest -q tests/test_archive.py tests/test_config.py tests/test_models.py` | 通过：19 passed。 |
| `python -m ruff check src/vision_doctor/checkers/annotation.py tests/test_annotation_checker.py` | 通过：`All checks passed!`。 |
| `python -m compileall src/vision_doctor` | 通过：全部模块成功编译。 |
| `git diff --check` | 新文件执行 `git add -N` 后通过，退出码 0；只有 Windows LF/CRLF 转换提示。 |
| `git status --short` | 通过：仅显示阶段 0 至阶段 3 的允许文件为 intent-to-add。 |

没有跳过必需命令；未连接网络、数据库或外部服务。

### 12.7 已知限制与阶段 4 可依赖接口

- 文件级 missing/empty/orphan Issue 没有真实标签行或 bbox，因此相应字段为 `None`；所有可用路径和状态均保留在 metrics/evidence。
- 极小框判断使用 Parser 已读取的图片尺寸和归一化 bbox，不重复读取图片；阈值是像素宽、高、面积的“任一低于即提醒”规则。
- 当前只实现标注异常检查器；图片质量、重复图片、类别分布、评分、诊断和报告尚未实现。
- 后续阶段可依赖 `check_annotations()` 返回有稳定 ID 的 `list[Issue]`，并直接合并到报告；不得自动修改源标签。
- 后续阶段可依赖 Parser 对每一非空坏行最多保留一个结构化 `ParseErrorRecord`，并通过 `ImageRecord.label_status` 区分 missing、empty 与 present。

阶段 3 的所有必需验收项均已满足，状态为 **Complete**。该结论构成阶段 4 开始前的有效基线。

## 13. 阶段 4 实施记录

### 13.1 开始前实时复核

- Git 根目录为 `D:\比赛作品\作品1\阶段0`，分支为 `main`；仓库仍无首个提交，开始前 26 个阶段 0 至阶段 3 文件均显示为 intent-to-add。
- 已重新读取项目契约、状态文件、`config.py`、`models.py`、`parser.py`、标注检查器、现有 fixtures/测试和当前 Git diff；未发现适用的 `AGENTS.md`。
- `python -m pytest -q tests/test_parser.py tests/test_annotation_checker.py` 在修改前通过：15 passed。

### 13.2 实际变更

- 新建 `utils/images.py` 与包入口：使用 Pillow + NumPy 解码图片，计算灰度均值、离散 Laplacian 方差和 DCT pHash；单文件解码失败返回可隔离结果。
- 新建 `checkers/image_quality.py`：实现 `IMAGE_UNREADABLE`、`IMAGE_BLURRY`、`IMAGE_DARK`、`IMAGE_BRIGHT`、`IMAGE_LOW_RESOLUTION`，每个可测 Issue 保存实际值及触发阈值。
- 新建 `checkers/duplicates.py`：按 SHA-256 生成完全重复组，按 pHash 汉明距离生成近似重复组；每组含确定性 representative，完全重复桶只以 representative 参与近似比较，避免同一完全重复对重复记录。
- 新建 `checkers/distribution.py`：统计每类实例数、覆盖图片数、零实例类别、稀有类别阈值和 imbalance index。
- 兼容修改 `config.py`：图片质量默认阈值改为 80、45、210、320×320；pHash 默认阈值改为 4，并增加默认 2000 张的两两比较硬上限。
- 兼容修改 `models.py`：`DuplicateGroup` 增加 representative 和成对距离；`DistributionStats` 增加图片覆盖、显式 imbalance index、零实例类别和稀有阈值。原有构造字段保留。
- 新建三组测试；初次实施未修改 Parser。补充修复经用户明确授权后兼容修改 `parser.py` 和 `tests/test_parser.py`，并扩充图片质量链路测试；未修改 `tests/conftest.py`、标注检查器、依赖清单或其他白名单外文件。

### 13.3 启发式阈值与检测行为

- 模糊：离散 Laplacian 方差 `< 80`；过暗：灰度均值 `< 45`；过亮：灰度均值 `> 210`；低分辨率：宽或高 `< 320`。Issue metrics 同时包含实际宽高、灰度均值、Laplacian 方差和对应阈值。
- 完全重复按文件内容 SHA-256 分桶；近似重复采用 8×8 DCT pHash，汉明距离 `<= 4` 连成确定性分组。无法解码的图片不参与 pHash，但不会中止其他图片比较。
- 近似检测对完全重复桶使用一个 representative，再进行简单两两比较，时间复杂度 O(n²)、pHash 内存 O(n)。默认超过 2000 张图片会给出明确 `ValueError`，而不是无界运行；该实现只面向小型黑客松数据。
- 稀有类别严格使用 `count < max(10, 0.2 × 非零类别实例数中位数)`；零实例类别单独记录，不混入中位数。imbalance index 为非零类别最大/最小实例数；仅一个非零类别时固定为 1.0，避免单类别被判为失衡；全部为零时为 `None`。

### 13.4 实际测试结果

| 命令 | 结果 |
|---|---|
| `python -m pytest -q tests/test_parser.py tests/test_annotation_checker.py`（开始前） | 通过：15 passed。 |
| `python -m pytest -q tests/test_image_quality.py tests/test_duplicates.py tests/test_distribution.py` | 首次在收集阶段因当前环境没有 `cv2` 而 2 errors；改用已可用的 Pillow + NumPy 后通过：7 passed。 |
| `python -m pytest -q tests/test_annotation_checker.py tests/test_parser.py tests/test_archive.py` | 通过：25 passed。 |
| `python -m ruff check src/vision_doctor/checkers src/vision_doctor/utils tests` | 首次发现 1 个导入排序问题；修复后通过：`All checks passed!`。 |
| `python -m compileall src/vision_doctor` | 通过：全部模块成功编译。 |
| `python -m pytest -q`（补充全量回归） | 通过：41 passed。 |
| `git diff --check` | 通过，退出码 0；只有 Windows LF/CRLF 转换提示。 |
| `git status --short` | 通过，退出码 0；仅显示阶段 0 至阶段 4 的文件为 intent-to-add。 |

没有跳过必需命令；没有连接网络、数据库或外部服务。

### 13.5 已验证接口与限制

- `check_image_quality(manifest, dataset_root, config=...) -> list[Issue]` 已验证正常、模糊、暗、亮、低分辨率和损坏文件，并验证一个损坏文件不阻止随后图片检查。
- `find_duplicate_groups(manifest, dataset_root, config=...) -> list[DuplicateGroup]` 已验证完全重复、近似重复、非重复排除、稳定 representative、唯一图片对及规模上限。
- `calculate_distribution(manifest) -> DistributionStats` 已验证精确计数、图片覆盖、零实例、稀有类、失衡比例、单类别和全部零实例边界。
- Parser 对可解码图片继续生成完整 `ImageRecord`；损坏图片只在 `DatasetManifest.unreadable_image_paths` 中保留相对路径，不伪造宽高或哈希。`summary.image_count` 与总字节数包含所有发现的受支持图片，标签仍可独立解析。
- 损坏图片不参与基于像素的 pHash 或质量数值测量；其 `IMAGE_UNREADABLE` metrics 明确只有解码失败状态，这是无法解码时可获得的真实证据。

### 13.6 补充修复与复验

- 用户明确授权兼容修改 `src/vision_doctor/parser.py` 和 `tests/test_parser.py`。同时在阶段 4 原白名单内兼容扩展 `DatasetManifest`、图片质量检查器和对应测试。
- Parser 完整加载图片以验证实际可解码性；捕获单张图片解码错误，将其相对路径写入 `unreadable_image_paths`，继续解析标签与后续图片。
- 图片质量检查器先把该结构化路径证据转换为稳定的 `IMAGE_UNREADABLE`，再检查所有可解码 `ImageRecord`。端到端测试直接调用 `parse_yolo_dataset()` 后调用 `check_image_quality()`，不再手工伪造损坏图片记录。
- `python -m pytest -q tests/test_parser.py tests/test_image_quality.py`：14 passed。
- `python -m pytest -q tests/test_image_quality.py tests/test_duplicates.py tests/test_distribution.py`：7 passed。
- `python -m pytest -q tests/test_annotation_checker.py tests/test_parser.py tests/test_archive.py`：26 passed。
- `python -m ruff check src/vision_doctor/checkers src/vision_doctor/utils tests`：`All checks passed!`。
- `python -m compileall src/vision_doctor`：通过。
- `python -m pytest -q`：42 passed。

阶段 4 的独立功能、历史回归和损坏图片真实链路均已通过，状态为 **Complete**。可以进入下一阶段；下一阶段开始前仍须按实时仓库状态重新复验。

## 14. 阶段 5 实施记录

### 14.1 开始前实时复核

- Git 根目录仍为 `D:\比赛作品\作品1\阶段0`，分支为 `main`，仓库无首个提交；开始前 34 个阶段 0 至阶段 4 文件均为 intent-to-add。
- 已重新读取项目契约、状态记录、config、models、archive、parser、全部 checkers、图片工具、全部现有测试和当前 Git diff；未发现适用的 `AGENTS.md`。
- `python -m pytest -q tests/test_annotation_checker.py tests/test_image_quality.py tests/test_duplicates.py tests/test_distribution.py` 在修改前通过：11 passed。

### 14.2 Health Score 方法

- 新建 `scoring.py`，严格按 `100 - structural - bbox - image - duplicates - distribution` 计算，并将五类扣分分别限制为 25、20、20、15、20；总分再次限制到 0–100。
- structural 比例按受影响结构项相对图片数计算；bbox 比例按 bbox Issue 相对合法标注与 bbox Issue 总数计算；image 和 duplicates 按受影响图片比例计算。所有原始比例均限制到 0–1。
- distribution 对单类别数据集固定为 0；多类别取零实例比例、稀有类别比例、经 10:1 饱和归一化的不平衡指数三者最大值。该规则与原始统计同时写入报告，属于可解释启发式而非模型精度预测。
- `LABEL_EMPTY` 明确排除在扣分 code 集合外。输出含 overall、A/B/C/D/F 等级、各类 penalty、raw ratio、五项 breakdown、逐项公式说明、方法版本和免责声明。
- 测试覆盖满分单类别、空标签不扣分、每类封顶、总分下限、稳定重复计算和五项 breakdown。

### 14.3 Pipeline 与模型兼容修改

- 新建 `pipeline.py`，执行 `ZIP → safe extract → parse → annotation/image checkers → duplicate/distribution → score → AuditReport`；函数不导入 Streamlit、数据库或网络客户端。
- Pipeline 使用安全解压上下文，返回报告前已完成所有依赖临时文件的检查；上下文退出后自动清理解压目录。严重 ZIP/数据集结构错误继续使用现有可读 `ArchiveError`/`DatasetParseError`。
- `AuditReport.diagnosis` 兼容改为可空且默认 `None`，符合本阶段不接入 LLM 的要求。`HealthScore` 增加等级、扣分、原始比例和说明字段，并通过模型校验保持等级与总分一致。
- Pipeline 将最终确定性 Issue 数写回 manifest summary；`AuditReport.model_dump_json()` 和 `AuditReport.model_validate_json()` 的往返已通过测试。

### 14.4 Demo 数据与 Smoke Test

- 新建 `scripts/generate_demo_dataset.py`，固定 NumPy 随机种子 `20261016`、ZIP 条目顺序、时间戳、权限和压缩参数；不联网。测试对两个独立输出执行逐字节比较并通过。
- 合成 ZIP 包含正常、缺失标签、空标签、四列错误、非法 class、越界框、极小框、损坏/模糊/暗/亮/低分辨率图片、完全重复、近似重复、孤立标签和三类别失衡。
- 新建 `scripts/smoke_test.py`，在独立临时目录生成 ZIP 并运行完整 Pipeline，校验全部预期 code、exact/near 分组及 JSON schema 往返。
- 新建 `demo/README.md`，记录生成和 Smoke 命令。按严格文件白名单，实际命令生成的约 4.9 MB `demo/visiondoctor_demo.zip` 在验证后清理；它是可由脚本随时重建的派生产物，不是源文件或互联网下载数据。
- Smoke Test 实际结果：15 张图片、14 个 Issue、12 类预期 Issue code、exact/near 两种重复组、Health Score 61.93、等级 D、`diagnosis=null`、schema `1.0.0`。

### 14.5 实际测试结果

| 命令 | 结果 |
|---|---|
| 阶段 4 四组 checker 测试（开始前） | 通过：11 passed。 |
| `python scripts/generate_demo_dataset.py` | 通过：生成 `demo/visiondoctor_demo.zip`；验证后按白名单清理。 |
| `python -m pytest -q tests/test_scoring.py tests/test_pipeline.py` | 通过：4 passed。 |
| `python scripts/smoke_test.py` | 通过：完整 ZIP→AuditReport 流程及预期结果全部满足。 |
| `python -m pytest -q` | 通过：46 passed。 |
| `python -m ruff check src scripts tests` | 首次发现 6 个导入格式/冗余类型注解问题；修复后通过：`All checks passed!`。 |
| `python -m compileall src scripts` | 通过。 |
| `git diff --check` | 通过，退出码 0；只有 Windows LF/CRLF 转换提示。 |
| `git status --short` | 通过，退出码 0；仅显示阶段 0 至阶段 5 的允许源文件为 intent-to-add，生成的 Demo ZIP 已清理。 |

没有跳过必需命令，没有连接网络、数据库、LLM 或其他外部服务。

### 14.6 已知限制与下一阶段接口

- 本阶段只允许 `diagnosis=None`，尚未实现 deterministic diagnosis 或 LLM；报告 JSON/HTML、Issue Explorer 和 Streamlit 完整界面仍是后续工作。
- Health Score 是启发式风险指标。分布不平衡在 10:1 时达到该类别最大扣分；规则版本为 `1.0.0`，后续调整必须改变方法版本并更新测试。
- Demo ZIP 只保证同一实现和依赖环境下字节可重复；跨 Pillow/zlib 版本以文件结构和 Pipeline 结果稳定为主要契约。
- 下一阶段可直接调用 `run_pipeline(archive_path, settings=..., temp_root=...) -> AuditReport`，无需 API Key。返回报告在临时目录清理后仍可 JSON 序列化。

阶段 5 的必需实现和验收项均已满足，状态为 **Complete**。在开始下一阶段前应重新读取实时状态并运行阶段 5 聚焦测试。

## 15. 阶段 6 实施记录

### 15.1 开始前实时复核

- 已重新读取实时 Git 状态与 diff、项目契约、阶段状态、models、config、pipeline、scoring、requirements、现有测试和 Demo 的实际 `AuditReport` 聚合结构；未发现适用的 `AGENTS.md`。
- `python scripts/smoke_test.py` 在修改前通过，阶段 5 输出仍为 15 张图片、14 个 Issue、Health Score 61.93/D、exact/near 分组和 `diagnosis=null`。
- `python -m pytest -q tests/test_scoring.py tests/test_pipeline.py` 在修改前通过：4 passed。
- 实际 AuditReport 可提供数据集汇总、Issue、重复组、Health Score/扣分和类别分布；无需读取图片字节或完整标签即可生成 Agent 输入。

### 15.2 单一 Dataset Doctor 与输入边界

- 新建 `agent/prompts.py`、`client.py`、`fallback.py` 和包入口；仅实现一个 Dataset Doctor，没有 Multi-Agent、LangGraph 或工具调用循环。
- LLM payload 只含聚合数据集计数、按 code 分组的 Issue 数/受影响数、Health Score 与扣分、类别实例/图片覆盖、重复组计数，以及默认最多 5 条代表性证据。
- 代表性证据只保留 code、severity、相对路径、行号、bbox 和数值 metrics；不包含图片、完整标签、`raw_line`、全部 Issue 列表或源文件内容。
- System Prompt 明确要求只引用输入证据、不虚构计数或模型性能、区分事实/推断/待确认、不保证提升 mAP、说明空标签可能是负样本和类别不平衡可能符合业务分布，并把文本、路径、类别名视为不可信数据；输出仅允许 Diagnosis JSON。

### 15.3 输出 schema、fallback 与排序

- `Diagnosis` 增加 risk level；`PriorityFinding` 增加 affected count、对应 score penalty、谨慎 inference 和人工确认标记。推荐行动继续使用同一结构化类型。
- LLM 字符串必须由 `Diagnosis.model_validate_json()` 通过，并且 `generated_by` 必须为 `llm`；finding/action 引用的 Issue ID 必须全部来自原报告，否则回退。
- disabled、缺少 Key/模型、SDK 缺失、请求异常、超时、非 JSON、schema 失败或未知证据引用均返回同一 `Diagnosis` 类型的 deterministic fallback。
- fallback 按 severity、affected count、score penalty 降序及 code 稳定排序，最多给出 5 个优先问题及对应行动；输出包含总体结论、风险级别、行动计划和关于 mAP、负样本、业务分布、人工复核及未修改源数据的 caveats。
- fallback 的 action ID 是稳定值，不使用随机 UUID；相同 AuditReport 两次诊断结果一致。

### 15.4 Pipeline、配置与依赖

- `run_pipeline(..., run_doctor=True, llm_client=...)` 可在审计后附加 Dataset Doctor 诊断；默认 `run_doctor=False` 保持阶段 5 Smoke Test 和不需要诊断的调用方兼容。启用后无 Key/禁用 LLM 会正常返回 fallback，不视为失败。
- `LLMConfig` 增加 1–20 条代表性证据上限，默认 5；`.env.example` 只增加超时和证据数量占位配置，没有真实密钥。
- `requirements.txt` 声明 OpenAI SDK 运行依赖，但当前解释器实际探查为 `openai_sdk_available=False`。默认/fake 路径使用惰性导入，不需要 SDK 即可完整测试；真实 API 路径未验证。
- Client 不记录异常文本或 API Key。测试让 fake 异常主动携带测试密钥，最终 Diagnosis JSON 中未出现该值。

### 15.5 实际测试结果

| 命令 | 结果 |
|---|---|
| `python scripts/smoke_test.py`（修改前） | 通过；阶段 5 audit-only Smoke 输出 `diagnosis=null`。 |
| 阶段 5 scoring/pipeline 聚焦测试（修改前） | 通过：4 passed。 |
| Demo AuditReport 结构探查 | 成功；只输出字段名、聚合值和一条代表性 Issue，不含图片或完整标签。 |
| Agent 聚焦测试首次执行 | 12 passed、1 failed；失败原因是 Python tuple 与 JSON list 的表示差异，规范化 bbox 后复测通过。 |
| `python -m pytest -q tests/test_agent_fallback.py tests/test_agent_client.py tests/test_pipeline.py` | 通过：13 passed。 |
| `python scripts/smoke_test.py`（最终） | 通过；保持阶段 5 audit-only 兼容输出，`diagnosis=null`。 |
| `python -m ruff check src/vision_doctor/agent src/vision_doctor/config.py src/vision_doctor/pipeline.py tests` | 首次发现 2 个问题；增加外部 provider 全异常 fallback 的明确豁免并整理导入后通过。 |
| `python -m compileall src/vision_doctor` | 通过。 |
| `python -m pytest -q`（补充全量回归） | 通过：57 passed。 |
| `git diff --check` | 通过，退出码 0；只有 Windows LF/CRLF 转换提示。 |
| `git status --short` | 通过，退出码 0；仅显示阶段 0 至阶段 6 的允许文件为 intent-to-add。 |

未调用真实付费 API、未连接数据库或其他外部服务。

### 15.6 当前模式、限制与下一阶段接口

- 本阶段实际运行模式为 **deterministic fallback**：环境中无真实 Key，OpenAI SDK 也未安装。fake client 的合法 JSON 路径验证为 `generated_by="llm"`，但这不等同于真实 API 已验证。
- 阶段 5 的 `scripts/smoke_test.py` 不在本阶段修改白名单内，因此仍验证 audit-only 默认路径；Dataset Doctor 的完整无 Key Pipeline 路径由 `tests/test_pipeline.py` 和 fallback 测试以 `run_doctor=True` 实际执行。
- Prompt 约束和 Issue ID 校验可降低幻觉风险，但无法证明外部模型永不在自由文本中产生不受支持的推断；UI/报告应继续清楚标记事实、推断和待确认项。
- 下一阶段可调用 `run_pipeline(..., run_doctor=True)` 获得必定非空的 `Diagnosis`；只有显式配置且成功校验的 LLM 才会替换 fallback。

阶段 6 的必需功能和验收项均已满足，状态为 **Complete**。下一阶段开始前应重新复验 Agent 聚焦测试及 Smoke Test。

## 16. DeepSeek API 兼容扩展记录

### 16.1 开始前实时复核

- 工作目录为 `D:\比赛作品\作品1\阶段0`，Git 分支仍为 `main`；仓库没有首个提交，阶段 0 至阶段 6 文件均为 intent-to-add。未发现适用的 `AGENTS.md`。
- 已重新读取 requirements、环境示例、忽略规则、状态文件、config、models、pipeline、全部 Agent 模块、阶段 6 测试、Smoke Test 及当前 Git 状态/diff。
- 修改前 `python --version` 为 3.11.7，系统解释器的 OpenAI SDK 探查结果为 `None`。
- 修改前阶段 6 聚焦回归通过：`13 passed in 12.44s`，确认既有 fallback/pipeline 基线有效。

### 16.2 实际变更与安全边界

- `LLMConfig` 现支持 `openai` 与 `deepseek` provider、可选 `base_url` 和原有模型/SecretStr Key/超时/重试/证据上限；DeepSeek 未显式配置地址时固定使用 `https://api.deepseek.com`。
- DeepSeek provider 只接受无用户名密码、无查询/fragment、无额外路径的官方 HTTPS origin；HTTP、相似恶意域名、用户信息和 `/v1` 等非官方形式会被 Pydantic 拒绝，避免把 Key 发给任意端点。
- `OpenAICompatibleDatasetDoctorClient` 使用 OpenAI SDK Chat Completions，发送 system/user 两条消息、`response_format={"type":"json_object"}`、`stream=False`、最多 1500 输出 token；DeepSeek 请求关闭 thinking。只有聚合统计和有限代表性证据进入既有 Prompt，未扩大数据边界。
- 空响应、非 JSON、schema 不匹配、provider 异常、超时及未知 Issue ID 仍统一回退到 deterministic `Diagnosis`；异常内容、请求头、Key 和完整原始响应均不记录。
- 新增 `scripts/verify_deepseek.py`。脚本默认不联网；只有 `VISION_DOCTOR_LIVE_API_TEST=1`、LLM enabled、provider/model/Key 完整时才运行一次。脚本强制 SDK `max_retries=0`，只输出 provider、model、generated_by 和 schema/验证布尔值，不输出 Key、完整 Prompt 或原始响应。
- `.env.example` 只包含 DeepSeek 占位 Key 和禁用的实时开关；`.env` 与 `.venv/` 均由 `.gitignore` 忽略。没有创建 `.env`，也没有发现已配置的 API Key。
- 测试增加 DeepSeek 环境加载、官方默认地址、恶意地址拒绝、fake SDK 构造参数、Chat JSON 请求、空/非法/schema/超时/网络/API 错误 fallback、缺 Key 不构造 SDK 及异常不记录测试 Key。普通 pytest 没有真实网络请求。

### 16.3 依赖安装事实

- 创建了被忽略的项目虚拟环境 `.venv`。首次沙箱内安装因代理/网络权限失败；获得网络安装授权后，`requirements.txt` 和 `requirements-dev.txt` 安装成功。
- 虚拟环境实际版本包括 OpenAI SDK 2.54.0、pytest 8.4.2 和 Ruff 0.17.1。`requirements.txt` 原先已经声明 `openai>=1.0,<3`，本次无需修改依赖清单。
- `.venv` 不出现在 Git 状态中；没有提交或推送任何内容。

### 16.4 实际验证结果

| 命令/检查 | 真实结果 |
|---|---|
| 修改前阶段 6 聚焦测试 | 通过：13 passed。 |
| 首次修改后聚焦测试 | 收集失败：`config.py` 的类内返回注解提前求值；Ruff 同时发现一处导入顺序问题。加入延迟注解并整理导入后修复。 |
| config + Agent + Pipeline 聚焦测试 | 通过：25 passed。 |
| `python -m pytest -q tests/test_agent_fallback.py tests/test_agent_client.py tests/test_pipeline.py`（虚拟环境） | 通过：17 passed in 13.31s。 |
| `python -m pytest -q`（虚拟环境） | 通过：67 passed in 14.35s。 |
| `python -m ruff check src scripts tests`（虚拟环境） | 通过：`All checks passed!`。 |
| `python -m compileall src scripts`（虚拟环境） | 通过。 |
| `scripts/verify_deepseek.py` 默认保护 | 通过：实时验证未启用，没有请求外部 API。 |
| 实时开关开启但无 Key 的保护 | 通过：报告缺少 Key/模型配置并退出，没有请求外部 API。 |
| OpenAI SDK 探查 | 项目 `.venv` 为 2.54.0；系统解释器仍不作为项目验证环境。 |
| 2026-10-17 用户授权的单次实时验证 | 已执行一次，`max_retries=0`；进程退出码 1，输出 `generated_by="deterministic"`、`diagnosis_schema_valid=true`、`live_api_verified=false`。未重试，不能标记为真实 API 验证成功。 |
| `git diff --check` | 通过，退出码 0；只有 Windows LF 将来可能转换为 CRLF 的提示。 |
| `git status --short` | 通过，退出码 0；48 个阶段 0 至本扩展的源文件均为 intent-to-add，包含新验证脚本；`.venv` 和 `.env` 未出现。 |
| `git check-ignore -v .venv .env` | 通过：分别由 `.gitignore` 的 `.venv/` 与 `.env` 规则忽略。 |

没有创建提交、修改 Git 历史或推送远程。

### 16.5 当前模式与未验证事项

- 当前实际模式为 **deterministic fallback**。DeepSeek 兼容性已通过 mock/fake SDK 验证；真实 API 验证仍未成功。
- 用户已在被忽略的本地 `.env` 中配置 Key；本次只检查了 Key 是否存在，没有输出、记录或写入其内容。执行前确认 provider 为 DeepSeek、模型存在、LLM enabled、base URL 为官方地址且重试数为 0。
- 2026-10-17 经用户明确授权，命令仅临时开启 live opt-in 并执行一次验证脚本。脚本返回 schema 有效的 deterministic fallback 和 `live_api_verified=false`，没有执行第二次请求。
- Client 按安全设计吞掉 provider 异常并禁止记录 Key、请求头和完整响应，因此现有证据无法区分超时、鉴权/余额/API 错误、空响应、非 JSON、schema 失败或未知 Issue 引用。实际 token 计费也无法从 fallback 输出确认；账户侧可能记录本次请求或费用，应以 DeepSeek 控制台为准。
- 只有后续经再次明确授权的请求输出 `generated_by="llm"`、`live_api_verified=true` 且 Diagnosis 通过 Pydantic 校验，才可把真实 DeepSeek API 标记为已验证。

## 17. DeepSeek 失败原因脱敏诊断记录

### 17.1 开始前复核

- 已读取用户提供的完整任务提示、实时 Git 状态/diff、全部适用说明文件、Agent/config/models/pipeline、验证脚本和相关测试；未发现适用的 `AGENTS.md`。
- `.venv` 和本地 `.env` 均存在；只检查了 Key 是否配置，没有读取、输出或修改 Key 内容。
- 修改前聚焦命令通过：`17 passed in 14.26s`。实时开关在整个本任务中保持关闭。

### 17.2 实际修改

- 修改 `src/vision_doctor/agent/client.py`：新增 `LLMFailureStage`、不可变 `DiagnosisOutcome`、`diagnose_report_with_status()`、专用空响应异常和纯类型错误分类；现有 `diagnose_report()` 继续只返回 `Diagnosis`。
- 修改 `src/vision_doctor/agent/__init__.py`：导出新的结构化结果、失败阶段和详细诊断入口。
- 修改 `scripts/verify_deepseek.py`：先执行 audit-only pipeline，再只调用一次详细诊断入口；输出增加脱敏 `failure_stage`，并继续强制 `max_retries=0`。
- 修改 `tests/test_agent_client.py`：增加未尝试状态、Provider 异常类型、空响应、非 JSON、Schema、generated_by、未知 Issue ID、原始响应不保留和兼容 wrapper 测试。
- 更新本状态文件。没有修改 config、models、pipeline、prompts、fallback、依赖清单、fallback 测试或 pipeline 测试。

### 17.3 失败阶段与安全边界

- 未尝试状态：`llm_disabled`、`credentials_missing`、`model_missing`。
- Provider/运行错误：`sdk_unavailable`、`request_timeout`、`authentication_error`、`rate_limit_or_balance_error`、`connection_error`、`provider_api_error`、`unknown_error`。
- 响应/验证错误：`empty_response`、`invalid_json`、`diagnosis_schema_error`、`generated_by_mismatch`、`unknown_issue_reference`。
- 异常只按 Python 异常类型或校验阶段分类，不读取或保留 `str(exc)`。结构化结果不含 Key、异常文本、HTTP 正文、请求头、完整 Prompt 或原始模型输出。
- `diagnose_report_with_status()` 成功时返回 LLM Diagnosis、`failure_stage=None` 和 `live_api_verified=true`；所有 fallback 返回 deterministic Diagnosis、明确失败阶段和 `live_api_verified=false`。
- `diagnose_report()` 通过新入口取得 `.diagnosis`，因此 pipeline 与原调用方接口保持兼容。

### 17.4 实际验证结果

| 命令/检查 | 真实结果 |
|---|---|
| 修改前 Agent/fallback/pipeline 聚焦测试 | 通过：17 passed。 |
| 首次修改后的聚焦测试 | 通过：33 passed。 |
| 首次聚焦 Ruff | 失败：发现 `agent/__init__.py` 和测试中的 3 个导入/`__all__` 排序问题；整理顺序后修复。 |
| 最终 Agent/fallback/pipeline 聚焦测试 | 通过：35 passed in 27.95s。 |
| 最终聚焦 Ruff | 通过：`All checks passed!`。 |
| `python -m pytest -q`（项目虚拟环境） | 通过：85 passed in 29.05s。 |
| `python -m ruff check src scripts tests` | 通过：`All checks passed!`。 |
| `python -m compileall src scripts` | 通过。 |
| `python scripts/verify_deepseek.py`（live opt-in 关闭） | 通过：明确报告实时验证未启用；没有构造 SDK、访问网络或产生费用。 |

### 17.5 当前结论与后续限制

- 本任务只完成离线代码修改、fake/mock 测试和默认保护验证，没有调用真实 DeepSeek API。
- 先前真实请求仍只能判定为 fallback，尚未获得新 `failure_stage`；不能用本次离线测试反推其确切失败原因。
- 2026-10-17 在本节离线改造完成后，用户再次明确授权了一次实时请求。执行前只确认 `.env` 存在、provider/model/Key 已配置、LLM enabled、官方 base URL 和 `max_retries=0`，没有输出 Key。
- 该命令只临时开启 live opt-in，实际执行一次且没有重试；退出码 1，返回 `failure_stage="invalid_json"`、`diagnosis_schema_valid=true`、`generated_by="deterministic"`、`live_api_verified=false`。
- `invalid_json` 表明 Provider 调用返回了非空内容，但该内容无法被 `json.loads()` 解析；系统未保留或输出原始响应，因此不能从本次记录判断具体文本形态。它不是本地缺 Key、LLM disabled、模型缺失、SDK 缺失、显式鉴权错误、网络连接错误或请求超时分类。
- 当前真实 API 严格状态仍为“未验证成功”，但 deterministic fallback 按项目契约可完整运行。阶段 7 的 Issue Explorer 与 JSON/HTML 报告依赖结构化 `AuditReport`/`Diagnosis`，不依赖真实 LLM 成功，因此本结果不构成阶段 7 阻塞项。
- 未提交、未推送，也没有修改 Git 历史。

## 18. 阶段 7 实施记录

### 18.1 开始前实时复核

- 已重新读取项目契约、状态文件、models、pipeline、全部 Agent 模块、requirements、现有相关测试、Smoke Test 和当前 Git 状态/diff；未发现适用的 `AGENTS.md`。
- `python -m pytest -q tests/test_agent_fallback.py tests/test_pipeline.py` 在修改前通过：5 passed in 5.57s。
- `python scripts/smoke_test.py` 在修改前通过：15 张图片、14 个 Issue、exact/near 重复组、Health Score 61.93/D、`diagnosis=null`、schema `1.0.0`。
- 使用 `Settings(_env_file=None)` 生成并检查实际 Demo `AuditReport`：顶层包含 schema、生成元数据、manifest、issues、duplicate groups、distribution、health score 和 diagnosis。本次检查没有读取 `.env`、没有构造真实 SDK 客户端、没有访问网络。

### 18.2 实际修改与接口

- 新建 `reports/json_report.py`：`render_json_report()` 以稳定对象键序、UTF-8 和禁止 NaN 的方式输出完整报告；`write_json_report()` 写入已完整渲染的内容；`load_json_report()` 使用 `AuditReport.model_validate_json()` 重新验证。
- 新建 `reports/html_report.py`：`render_html_report()` 输出无 CDN、无脚本、无原始图片的自包含 HTML；`write_html_report()` 写入 UTF-8 文件。报告包含数据集概览、Health Score、扣分与 component breakdown、Issue 汇总及证据、类别分布、重复组、Dataset Doctor 诊断、修复行动、caveats、生成时间及阈值快照。
- 所有来自 manifest、类别名、路径、Issue、metrics 和 diagnosis 的动态文本均经 `html.escape(..., quote=True)` 处理；测试攻击字符串不能形成 `<script>` 或 `<img>` 元素。
- `reports/__init__.py` 导出 JSON/HTML 的 render/write/load 公共接口。
- `AuditReport` 新增向后兼容的 `threshold_snapshot` 字段，默认空字典；Pipeline 记录本次实际 upload、image-quality、duplicate-detection 配置，图片扩展名排序后写入以保持稳定。
- 修改 `tests/test_pipeline.py` 验证阈值快照及其 JSON round-trip；新建 `tests/test_reports.py` 覆盖 UTF-8 round-trip、自包含 HTML、无 diagnosis、fallback、模拟 LLM diagnosis、攻击字符串转义及写入失败不改变分析对象。
- 本阶段实际修改 8 个允许文件：`models.py`、`pipeline.py`、reports 下 3 个文件、`tests/test_pipeline.py`、`tests/test_reports.py` 和本状态文件。`requirements.txt` 已有 Jinja2 且本实现无需新增依赖，因此未修改；未修改 UI 或其他业务文件。

### 18.3 失败、修复与真实验证结果

| 命令/检查 | 真实结果 |
|---|---|
| 首次报告聚焦测试 | 6 passed、2 failed；Windows 沙箱允许创建临时文件但拒绝 `os.replace`。改为先在内存完整渲染、再直接写入，并保留写入失败不改变 `AuditReport` 的测试后修复。 |
| 修复后的报告/pipeline 聚焦测试 | 通过：8 passed in 7.52s。 |
| `python -m pytest -q tests/test_reports.py tests/test_pipeline.py`（最终） | 通过：8 passed in 7.23s。 |
| `python -m pytest -q tests/test_agent_fallback.py tests/test_scoring.py` | 通过：4 passed in 2.85s。 |
| `python -m pytest -q` | 通过：90 passed in 32.30s。 |
| `python -m ruff check src/vision_doctor/reports tests/test_reports.py` | 通过：`All checks passed!`。 |
| `python -m compileall src/vision_doctor` | 通过。 |
| 报告公共接口直接导入检查 | 首次因 src layout 未设置 `PYTHONPATH` 而失败；设置 `PYTHONPATH=...\\src` 后通过：`report_imports=ok`。pytest 继续由既有 `tests/conftest.py` 配置导入路径。 |
| `git diff --check` | 通过，退出码 0；只有 Windows LF 将来可能转换为 CRLF 的提示。 |
| `git status --short` | 通过，退出码 0；51 个阶段 0 至阶段 7 文件为 intent-to-add 或未跟踪，没有生成的 Demo ZIP、`.env` 或 `.venv`。 |

阶段 7 要求的命令均已执行，没有跳过。额外运行了完整测试。结构检查时一度生成的 `demo/visiondoctor_demo.zip` 已在确认绝对路径后清理，未保留白名单外产物。没有调用 API、连接数据库、提交或推送 Git。

### 18.4 已知限制与下一阶段判断

- HTML 当前不含缩略图，避免报告体积和隐私风险；它展示的是相对路径与结构化证据。大型 Issue 列表会使 HTML 线性增长，当前没有分页或折叠 UI。
- 报告先完整渲染到内存，因此非常大的审计结果会占用与输出规模相当的额外内存。Windows 沙箱不支持本次尝试的同目录原子替换；写入异常会向调用方抛出，但不会修改或丢失内存中的 `AuditReport`。
- 真实 DeepSeek API 仍未验证成功，最后一次授权请求为 `invalid_json` fallback；这不影响 JSON/HTML 报告或后续 Streamlit Demo 使用 deterministic diagnosis。
- 阶段 7 验收项均满足，状态为 **Complete**，没有阻塞项。可以进入阶段 8；开始前仍须读取实时状态、复验报告/pipeline，并以阶段 8 的明确白名单为准。

## 19. 阶段 8 实施记录

### 19.1 开始前实时复核

- 已重新读取项目契约、状态文件、app、config、models、pipeline、reports、agent、Demo 脚本、相关测试和实时 Git 状态；未发现适用的 `AGENTS.md`。
- `python scripts/generate_demo_dataset.py` 通过，在 `demo/visiondoctor_demo.zip` 生成确定性测试归档；最终验证后已清理该派生产物。
- `python scripts/smoke_test.py` 通过：15 张图片、14 个 Issue、exact/near 重复组、Health Score 61.93/D、`diagnosis=null`、schema `1.0.0`。
- `python -m pytest -q tests/test_pipeline.py tests/test_reports.py tests/test_agent_fallback.py` 通过：10 passed in 9.58s。
- 开始前 Pipeline、fallback 和报告接口均可用；本阶段未根据状态文档代替运行验证。

### 19.2 实际 UI 与安全实现

- `app.py` 现为可直接启动的 Streamlit 入口，使用一个页面和固定四个 tabs：Upload、Dashboard、Issue Explorer、AI Doctor & Report；增加页面级通用错误兜底，不向用户呈现异常对象、堆栈或密钥。
- `ui/upload.py` 将上传字节保存到 `TemporaryDirectory(prefix="vision-doctor-ui-")`，只接受 `.zip`，在读取分析前检查配置的大小上限，并调用现有安全 Pipeline。界面显示格式、资源限制、临时处理声明和可调图片质量/近重复阈值。
- 外部 LLM 复选框默认关闭；关闭时即使本地 `.env` 启用了 DeepSeek，也把本次 UI 配置中的 LLM 禁用并生成完整 deterministic fallback。开启时明确提示可能产生外部请求和费用。
- `ui/state.py` 通过 session state 保存报告和临时 workspace；选中的上传发生变化时立即清理旧 workspace，成功替换结果时也先清理旧临时数据。没有把上传文件写入仓库或数据库。
- Dashboard 显示 Health Score、图片/标签/目标/类别计数、四级 severity 数量、类别分布、扣分构成和图片质量汇总。
- Issue Explorer 提供 code、severity、split、class 四维筛选和分页；展示相对路径、标签行、bbox、metrics、阈值、建议及图片预览。`utils/images.py` 只从会话 ZIP 中读取唯一、安全的相对路径，限制单文件大小、解码并缩放为 PNG，可叠加异常框；损坏或无法唯一匹配时返回友好无预览状态。
- Issue Explorer 展示 exact/near 重复组、representative、距离，并将组内图片最多三列并排预览。预览不修改原图，不写入仓库。
- Doctor 面板显示实际 `generated_by` 对应的 LLM 或 deterministic fallback 模式、assessment、risk、findings、action plan 和 caveats。报告面板从同一 `AuditReport` 在内存中生成非空 JSON/HTML 下载。
- 本阶段实际修改 11 个允许文件：`app.py`、UI 包入口和 6 个 UI 模块、`utils/images.py`、`tests/test_ui_smoke.py`、本状态文件。没有修改 Pipeline、models、config 或 requirements，因为现有接口和依赖已满足集成要求。

### 19.3 自动化和服务启动证据

| 命令/检查 | 真实结果 |
|---|---|
| 首次 `AppTest` 驱动 | 当前 Windows 沙箱中的 Streamlit 1.66 驱动长时间无输出；主测试进程和单测定位各中断一次。`python app.py` 可在约 3 秒完成裸模式执行，因此改用入口导入/四标签契约测试及单独服务启动验证。 |
| `python -m pytest -q tests/test_ui_smoke.py tests/test_pipeline.py tests/test_reports.py` | 通过：12 passed in 9.54s。 |
| `python -m pytest -q` | 通过：94 passed in 36.16s。 |
| `python -m ruff check app.py src tests` | 通过：`All checks passed!`。首次聚焦 Ruff 发现 3 个可修复的 import/noqa 问题，修复后全量通过。 |
| `python -m compileall app.py src` | 通过。 |
| 沙箱内 `streamlit run app.py --server.headless true` | 进程保持但未绑定回环端口，HTTP 探测失败；已停止，没有把它误记为启动成功。 |
| 放行本机端口后的服务启动 | 使用同一 app、headless 模式、关闭 usage statistics 并指定 8505 端口；终端确认 Uvicorn 启动，`http://127.0.0.1:8505` 返回 HTTP 200 且页面包含 Streamlit 标识，随后用 Ctrl+C 停止。 |
| Demo UI 集成测试 | 通过：上传字节→临时 workspace→完整 Pipeline→deterministic diagnosis→框/质量 Issue 筛选→PNG 框预览→exact/near 组→JSON Pydantic round-trip/HTML 下载；workspace cleanup 后目录不存在。 |
| `git diff --check` | 通过，退出码 0；只有 Windows LF 将来可能转换为 CRLF 的提示。 |
| `git status --short` | 通过，退出码 0；58 个阶段 0 至阶段 8 文件为 intent-to-add 或未跟踪；`.env`、`.venv` 和生成的 Demo ZIP 未出现。 |

没有进行真实 API 请求、数据库连接、Git 提交或推送。自动测试显式使用 `Settings(_env_file=None)`，服务启动测试没有上传文件或触发分析。

### 19.4 未自动验证事项、限制与下一阶段判断

- 当前环境未自动操作真实浏览器的本地文件选择器、tab 点击和下载保存对话框。其底层 upload/session/filter/preview/download 数据链路已由测试直接执行，HTTP 服务启动也已独立验证；这些不等同于人工视觉验收。
- Streamlit `AppTest` 在本机沙箱中会挂起，未作为通过证据。若阶段 9 需要浏览器级验收，应在可交互浏览器中人工上传生成的 Demo ZIP，并逐 tab 核对布局、响应和下载文件。
- 会话关闭时依赖 `TemporaryDirectory` 对象释放；重新上传已明确、同步清理。进程被强制终止时可能由操作系统稍后清理系统临时目录。
- 图片预览按 ZIP 相对路径或唯一后缀匹配；存在多个相同后缀时安全拒绝预览。报告和结构化 Issue 仍可使用。
- 阶段 8 验收项均有自动化或服务启动证据，状态为 **Complete**，没有阻塞项。可以进入阶段 9；开始前应重新复验全量测试、Streamlit 启动、安全边界及未提交状态。

## 20. 阶段 9 实施与最终交付验收

### 20.1 开始前实时复核

- 工作根目录为 `D:\比赛作品\作品1\阶段0`，Git 分支为 `main`；仓库仍没有任何 commit，也没有配置 remote。所有阶段文件是 intent-to-add 或未跟踪状态，不能将此状态表述为已提交或已发布。
- 已读取项目契约、完整实施状态、全项目文件树、依赖清单、全部源码/测试/脚本、Demo 说明、`.env.example` 和 `.gitignore`；从当前目录向上未发现适用的 `AGENTS.md`。
- 修改前先执行 `python -m pytest -q`，真实结果为 94 passed in 35.93s；没有先按状态文件假设项目正确。
- 根目录原先没有 `README.md`；`demo/visiondoctor_demo.zip` 可重复生成但原先没有专用忽略规则。另有 4 个从早期阶段遗留、没有任何引用的空包文件，其文案仍声称对应功能“尚未实现”。

### 20.2 实际交付修改

- 新建 `README.md`，记录项目定位、已实现范围、Mermaid 数据流、两种 YOLO 布局、安装/启动/Demo/API Key/fallback/测试命令、Streamlit Community Cloud 部署、隐私与 ZIP 安全、Health Score 公式及免责声明、三分钟演示、截图占位说明、已知限制和后续方向。
- `.gitignore` 增加 `demo/visiondoctor_demo.zip`，防止把可重建的合成 ZIP 误提交；既有 `.env`、虚拟环境、上传、临时目录和生成报告规则保持不变。
- `demo/README.md` 增加 UI 启动、四标签人工核对和 Demo ZIP 不提交说明。
- 删除没有导入引用且内容已经失真的空占位文件：`checks/__init__.py`、`diagnosis/__init__.py`、`ingest/__init__.py`、`parsers/__init__.py`。实际实现继续位于 `checkers/`、`agent/`、`archive.py` 和 `parser.py`。
- 没有修改业务功能、测试、依赖版本或 Git 历史；没有增加数据库、训练流程、Multi-Agent 或新的产品范围。未创建 `LICENSE`，因为用户尚未指定授权条款，不应擅自选择法律许可。

### 20.3 最终命令与真实结果

| 命令/检查 | 真实结果 |
|---|---|
| `python --version` | 通过：Python 3.11.7。 |
| `python scripts/generate_demo_dataset.py` | 通过：生成 `demo/visiondoctor_demo.zip`；路径输出在当前终端发生中文 mojibake，但文件实际存在且规则命中 `.gitignore`。 |
| `python scripts/smoke_test.py` | 通过：15 张图片、14 个 Issue、12 种预期 Issue code、exact/near 重复组、Health Score 61.93/D、schema `1.0.0`。该脚本按设计不运行 Doctor，因此输出 `diagnosis=null`。 |
| `python -m pytest -q`（修改前） | 通过：94 passed in 35.93s。 |
| `python -m pytest -q`（最终独立完成进程） | 通过：94 passed in 50.51s；0 failed、0 skipped。首次并行采集只在 30 秒窗口返回进行中进度，未被当作完成证据，随后独立重跑并等待到最终汇总。 |
| `python -m pytest -q tests/test_reports.py tests/test_ui_smoke.py` | 通过：9 passed in 9.70s；覆盖无 Key deterministic diagnosis、上传临时目录清理、异常框/重复组预览，以及非空 JSON/HTML 下载和 JSON Pydantic round-trip。 |
| `python -m ruff check .` | 通过：`All checks passed!`。 |
| `python -m compileall app.py src scripts` | 通过；删除的空包目录仍存在于本地文件系统，所以 compileall 会列出目录名，但其中没有可提交文件。 |
| `git diff --check` | 通过，退出码 0；仅有 Windows LF→CRLF 提示，无 whitespace error。 |
| `git status --short` | 退出码 0；阶段文件仍为 intent-to-add/未跟踪，4 个旧 intent-to-add 占位文件显示为删除；`.env`、`.venv` 和 Demo ZIP 均未出现。 |
| `streamlit run app.py --server.headless true`（等价使用项目 Python module 入口，端口 8506） | 通过：Uvicorn 在 8506 启动，`http://127.0.0.1:8506` 返回 HTTP 200 且页面含 Streamlit 标识；随后 Ctrl+C 正常停止。停止动作使被中断的服务进程返回非零，不代表启动失败。 |
| `.gitignore` 命中检查 | `.env`、`.venv`、`.streamlit/secrets.toml` 和 `demo/visiondoctor_demo.zip` 均由预期规则忽略；上传、临时和生成报告目录也有规则。 |
| 数据库依赖扫描 | `requirements*.txt`、应用、源码、脚本和测试中未发现 PostgreSQL、Redis、SQLAlchemy、psycopg、MySQL 或 MongoDB 依赖/引用。 |
| 脱敏密钥扫描 | 排除本机 `.env`、虚拟环境、Git 元数据和 Demo ZIP 后，未发现符合长 `sk-...` 形式的潜在真实 Key；没有读取或显示 `.env` 内容。 |
| 首次组合安全审计命令 | 失败：PowerShell 对包含双引号的正则发生 parser error；该命令没有执行审计。随后拆分为安全的只读命令，忽略规则、数据库和潜在 Key 检查均成功。 |

### 20.4 MVP 契约逐项验收

| `MVP_SPEC.md` 条件 | 证据与结论 |
|---|---|
| 1. 合法最小 YOLO ZIP 可从 Streamlit 端到端分析 | 满足：UI 集成测试以上传字节运行完整 Pipeline；服务 HTTP 200。真实浏览器文件选择仍列为人工验收。 |
| 2. 不安全/损坏/超限 ZIP 安全拒绝 | 满足：archive 自动化测试包含路径穿越、绝对路径、软链接、压缩炸弹候选、损坏和限制场景；全量测试通过。 |
| 3. 检查场景可重复且可定位 | 满足：Demo 固定随机种子；标注、图片质量、重复和分布测试全部通过，Issue 含路径/行号/metrics 等证据。 |
| 4. Health Score 可复算且有说明 | 满足：scoring/report 测试通过；报告包含五类比例、封顶扣分、说明、阈值快照和免责声明。 |
| 5. 无 API Key 可完整运行 | 满足：UI 集成显式使用 `Settings(_env_file=None)` 并得到 deterministic Diagnosis、预览和两种报告。 |
| 6. LLM 有校验、超时和 fallback | 满足：fake/mock 覆盖合法、空、非 JSON、schema、超时、网络和 API 错误；真实 DeepSeek 仍未验证成功，不影响此契约。 |
| 7. Issue Explorer 可筛选并展示证据 | 满足：code/severity/split/class 筛选、框/质量问题和重复组的数据链路有自动化证据；最终视觉排版需人工确认。 |
| 8. JSON/HTML 来源一致 | 满足：由同一 `AuditReport` 构建，JSON round-trip 和 HTML 生成测试通过。 |
| 9. 不改原始数据、临时清理、HTML 转义 | 满足：只读分析、workspace cleanup 和攻击字符串转义均有测试。强制终止进程时的系统临时目录清理由 OS 负责，已记录限制。 |
| 10. 文档与真实状态一致 | 满足：README 命令均在当前布局执行；明确记录未部署、未提交、真实 DeepSeek 未成功和浏览器人工验收项。 |

### 20.5 提交与 Demo 链接判断

- **代码内容可以进入提交/推送步骤**：所有本地必需质量门禁有通过证据，阶段 9 状态为 Complete。提交前用户仍需检查完整 diff，然后执行 `git add -A`、首次 commit、配置 GitHub remote 并 push；本任务没有代为执行这些动作。
- **目前还没有可提交的代码仓库链接**：本地仓库无 commit、无 remote，因而不存在经验证的 GitHub URL。
- **目前还不能提交 Demo 链接**：没有执行外部部署，也没有线上 URL。用户需按 README 将仓库推送到 GitHub、在 Streamlit Community Cloud 选择 `app.py` 部署，并用 Demo ZIP 人工复验四个标签页和下载后，才能提交该链接。
- 如果赛事要求“仓库链接 + 在线 Demo 链接”同时交付，则当前整体状态是“本地包已验收，外部发布待用户完成”，不是已经可直接填写两个链接。

### 20.6 已知限制与部署前用户动作

- 真实 DeepSeek API 最后一次授权请求返回不可解析内容并使用 fallback，尚未取得 `generated_by=llm`；无 Key 演示不受影响。
- 未自动操纵真实浏览器文件选择和下载对话框，也未制作截图。部署前应按 README 的三分钟流程做一次人工视觉验收并截取真实画面。
- 用户需选择许可证；在此之前仓库没有 `LICENSE`。
- Streamlit Community Cloud 部署步骤依据 2026-10-17 查阅的官方文档：根目录入口/requirements 布局可用，根级 secrets 可作为环境变量。线上构建、域名、账号权限和公网访问均未验证。
- 下一步是用户审核 diff、提交并推送 GitHub，再部署 Community Cloud；阶段 9 不自动 commit、push 或 deploy。

## 21. Split-first 数据集结构与发布更新（2026-10-19）

### 21.1 实际变更

- 唯一支持的布局调整为 `train/images`、`train/labels`、`val/images`、`val/labels`，以及可选的同构 `test` split；旧式 `images/train`、`labels/train` 布局会返回明确结构错误。
- Parser 现在通过唯一的 `data.yaml` 定位数据集根，支持 ZIP 直接以数据集内容为根或包含一个外层 `dataset/` 目录。ZIP 根和数据集根中的其他普通文件会被忽略；多个 `data.yaml` 会因目标歧义被拒绝。
- Pipeline 使用解析后的真实数据集根执行图片质量和重复检测，避免外层目录导致文件定位失败。缺失标签的期望路径逻辑支持 split-first 布局。
- Demo ZIP 改为 `dataset/train|val|test/images|labels`，包含额外说明文件以验证忽略行为；仍保持固定随机种子、成员顺序和 ZIP 元数据。
- README、Demo 说明、上传页面和 MVP 契约已同步更新。相关 parser、annotation、duplicate、image-quality、pipeline 与 UI 测试均使用新结构。
- DeepSeek JSON 输出上限从 1500 调整为 4000 tokens，并在 Prompt 中增加精简的 JSON 示例和长度约束。代表性证据现在包含真实 `issue_id`，并明确要求模型只能引用这些 ID；未知 ID 的拒绝逻辑保持不变。

### 21.2 真实验证结果

| 命令/检查 | 真实结果 |
|---|---|
| `python scripts/generate_demo_dataset.py` | 通过；生成新的 split-first `demo/visiondoctor_demo.zip`（该派生产物继续被 Git 忽略）。 |
| `python scripts/smoke_test.py` | 通过：15 张图片、14 个 Issue、12 种预期 Issue code、exact/near 重复组、Health Score 61.93/D。 |
| 首次完整 `python -m pytest -q` | 94 passed、3 failed；失败均为仍构造旧目录的 duplicate/image-quality 测试，更新 fixture 后修复。 |
| 修复后的 `python -m pytest -q` | 通过：97 passed in 37.91s。 |
| `python -m ruff check .` | 通过：`All checks passed!`。 |
| `python -m compileall app.py src scripts` | 通过。 |
| `git diff --check` | 通过，退出码 0；仅有 LF→CRLF 提示。 |
| 第一次沙箱实时 API 尝试 | `connection_error`，安全回退；没有作为远程成功证据。 |
| 放行网络后的第一次响应 | `invalid_json`，安全回退；增加 JSON 示例并提高输出上限。 |
| 第二次响应 | JSON 合法但为 `unknown_issue_reference`，安全回退；定位为 Prompt 未提供可引用的真实 Issue ID。 |
| 最终 opt-in 实时验证 | 通过：provider=`deepseek`、model=`deepseek-flash`、`generated_by=llm`、`live_api_verified=true`、`failure_stage=null`，Diagnosis 通过 Pydantic 校验。 |

实时验证只发送聚合统计、Issue 分组、Health Score、类别分布和最多 5 条代表性证据；没有发送图片、完整标签、完整 Issue 列表或完整数据集。输出和日志未包含 Key、请求头、完整 Prompt 或原始响应。

### 21.3 当前阶段状态

- 最终本地复验：Python 3.11.7；Demo 生成与 Smoke Test 通过；`python -m pytest -q` 为 97 passed in 37.50s；Ruff、compileall、`git diff --check` 均通过。
- Streamlit 在本机放行回环端口后于 8507 成功启动，`http://127.0.0.1:8507` 返回 HTTP 200 且页面含 Streamlit 标识，随后正常停止。沙箱内的首次探测因套接字权限失败，未被记为应用启动证据。
- `.env`、`.venv`、`.streamlit/secrets.toml` 和 `demo/visiondoctor_demo.zip` 均继续命中 `.gitignore`，未出现在 Git 状态中。
- 本次兼容修改与本地验证已完成。提交、推送和 Streamlit Cloud 重新构建结果将在发布后补记；在这些步骤完成前，不把外部发布更新描述为完成。

### 21.4 外部发布与线上复验

- split-first 兼容修改已提交并推送到 GitHub `main` 分支；Streamlit Community Cloud 随后执行了应用重启并拉取最新代码。
- GitHub 仓库：`https://github.com/willbanksfassler-cpu/VisionDoctor`。
- Streamlit Demo：`https://visiondoctor-2ttszahu2sph93rcmt9a3h.streamlit.app/`。
- 云端上传页已实际显示 `train/images`、`train/labels`、`val/images`、`val/labels` 和可选 `test` 的新版说明，不再显示旧式 `images/train` 结构。
- 已将本地重新生成且被 Git 忽略的 `demo/visiondoctor_demo.zip` 上传到云端页面，并完成一次线上分析：页面报告 `Dataset health check complete`；Dashboard 显示 Health Score 61.9/100、15 张图片、15 个标签、21 个目标、3 个类别、0 critical、4 error、9 warning、1 info。
- Issue Explorer 显示 14 个问题，实际包含 bbox 问题、图片质量问题，以及 1 个 exact 和 1 个 near 重复组；路径采用 `train/...`、`val/...` 的 split-first 相对形式。
- AI Doctor & Report 在线运行模式为 deterministic fallback，risk 为 High，assessment、priority findings、action plan、caveats 以及 JSON/HTML 下载控件均非空。真实 DeepSeek API 已在本地 opt-in 验证中成功取得 `generated_by=llm` 并通过 Diagnosis 校验，但未把本机 Key 上传到 Streamlit Cloud。
- 浏览器自动化的下载保存事件在本次复验中超时，因此没有把新的自动下载文件记为通过证据；此前用户已人工确认两个报告下载及 JSON 校验成功。本次代码级报告 round-trip 和 HTML 生成仍由 97 项全量测试覆盖。
- `.env`、API Key、`.venv`、上传数据和 `demo/visiondoctor_demo.zip` 均未进入提交；没有执行 force push，也没有部署数据库。

## 22. 多布局 YOLO Parser 兼容更新（2026-10-19）

### 22.1 实时基线与问题定位

- 开始修改前重新读取了 README、MVP 契约、实施状态、忽略规则、环境变量示例、依赖、archive/parser/pipeline/models、annotation checker、上传 UI、Demo 生成脚本及相关测试；从当前目录向上未发现适用的 `AGENTS.md`。
- Git 基线为 `main`，`origin` 指向 `https://github.com/willbanksfassler-cpu/VisionDoctor.git`，工作区开始时干净，最新 commit 为 `eacbd0e Record split-first deployment verification`。
- 基线聚焦测试通过：36 passed in 7.76s；Python 为 3.11.7。
- 旧提示 `Dataset root must contain both images/ and labels/ directories.` 不存在于修改前的当前源码，判断为旧部署或旧版本消息；`Dataset split 'train' must contain both images/ and labels/ directories.` 来自修改前当前 Parser。通用 UI 提示来自 `safe_error_message` 对非预期异常的脱敏兜底。
- 修改前 Parser 固定读取 split-first 的 `train` 和 `val`，不使用 YAML 的 `path/train/val/test`，并把缺少 `labels/` 视为数据集级结构错误。这是常见 ZIP 上传失败的直接原因。

### 22.2 实际修改

- Parser 现在优先解析 `data.yaml` 中安全的相对本地 `path`、`train`、`val`、`test` 目录，并支持：`train/images` + `train/labels`、`images/train` + `labels/train`、同级 `images` + `labels` 三类布局；`val` 和 `test` 可选。
- `data.yaml` 的 `names` 必需；`nc` 可选但存在时必须为正整数且与 `names` 数量一致。YAML 解析、字段类型、目录存在性和路径安全错误均返回可读的 `DatasetParseError`。
- YAML 路径拒绝 URL、绝对路径、Windows 盘符/UNC 路径和越过数据集根的路径；多个真实 `data.yaml` 或多个可自动识别布局会被明确拒绝，避免猜测错误数据根。`__MACOSX` 中的元数据 YAML 不参与数据根判定。
- ZIP 根和数据集根可包含 README、许可证、`.DS_Store` 等其他普通文件。唯一真实 `data.yaml` 可以位于一个外层目录中。
- split 缺少 `labels/` 时继续解析图片，并由 annotation checker 产生逐图 `LABEL_MISSING`；损坏标签仍保留为行级解析错误。空的可选 `val`/`test` 占位目录被忽略，空的训练目录会返回明确错误。
- UI 上传说明、split 筛选、README、MVP 契约和 Demo 说明已同步；Demo YAML 现在显式声明 `path`、三个 split、`nc` 和 `names`。本轮没有扩展 COCO、分割、姿态、训练、数据库、Multi-Agent 或 LLM 能力，也没有调用真实付费 API。

### 22.3 测试与启动证据

| 命令/检查 | 真实结果 |
|---|---|
| 首次新增聚焦测试 | 39 passed、4 failed；失败暴露既有 annotation fixtures 中的空 `val` 占位目录，随后按“空的可选 split 忽略”规则修复。 |
| `python -m pytest -q tests/test_parser.py tests/test_annotation_checker.py tests/test_pipeline.py tests/test_ui_smoke.py` | 通过：43 passed in 6.53s。 |
| `python scripts/generate_demo_dataset.py` | 通过；重新生成被 Git 忽略的 `demo/visiondoctor_demo.zip`。 |
| `python scripts/smoke_test.py` | 通过：15 张图片、14 个 Issue、12 种预期 Issue code、exact/near 重复组、Health Score 61.93/D、schema `1.0.0`。 |
| `python -m pytest -q tests/test_archive.py tests/test_parser.py tests/test_annotation_checker.py tests/test_pipeline.py tests/test_ui_smoke.py` | 通过：54 passed in 8.30s。 |
| `python -m pytest -q` | 通过：115 passed in 41.69s；0 failed。 |
| `python -m ruff check .` | 通过：`All checks passed!`。 |
| `python -m compileall app.py src scripts` | 通过。 |
| `git diff --check` | 通过，退出码 0；仅有 LF→CRLF 提示。 |
| 沙箱内 Streamlit 探测 | 进程启动后回环探测被 Windows 套接字权限拒绝，未记作成功。 |
| 放行回环端口后的 Streamlit 启动 | 通过：8508 端口返回 HTTP 200 且响应含 Streamlit 标识，随后停止精确对应的临时 Python 进程。 |

新增/更新测试覆盖 train-only、可选 val/test、split-first、images-first、flat、YAML 混合路径、相对 `path`、缺失 labels、`nc` 一致性、字段类型、缺失目录、不安全路径、`__MACOSX`、歧义布局、Pipeline ZIP 集成、UI split 推断和可读错误透传。

### 22.4 当前状态与下一步

- 兼容性修改已提交为 `5da70f8 Support flexible YOLO dataset layouts` 并成功推送到 `origin/main`；GitHub 页面实际显示新提交和新版 README。首次沙箱内 push 因本机代理不可达失败，放行网络后的同一命令成功，没有 force push 或历史改写。
- Streamlit Community Cloud 在 push 后仍短暂显示旧版上传说明，随后在应用管理页明确执行一次 Reboot；重启后线上页面实际显示 split-first、images-first、flat 三种布局、可选 val/test 和缺失 labels 的新版说明。
- 已把本地重新生成且被 Git 忽略的 `demo/visiondoctor_demo.zip` 上传到现有 Demo，并保持“Use configured external LLM”未勾选。线上页面报告 `Dataset health check complete`，本次没有调用真实付费 API。
- Dashboard 实际显示 Health Score 61.9/100、15 张图片、15 个标签、21 个目标、3 个类别，以及 0 critical、4 error、9 warning、1 info。
- Issue Explorer 实际显示 14 个问题，包含 `BBOX_OUT_OF_RANGE`、`BBOX_TINY`、图片质量问题和 1 个 exact/1 个 near 重复组；路径同时包含 `train/...` 和 `val/...` 的 split-first 相对路径。
- AI Doctor & Report 实际显示 deterministic fallback、High risk、非空 assessment/findings/action plan/caveats 及两种下载按钮。
- 线上下载的 JSON 为 34,612 字节，`schema_version=1.0.0`，通过 `AuditReport.model_validate_json`，Health Score 为 61.93，`generated_by=deterministic`；HTML 为 15,488 字节，包含 HTML 文档声明和 Health Score 内容。
- GitHub 仓库为 `https://github.com/willbanksfassler-cpu/VisionDoctor`，Streamlit Demo 为 `https://visiondoctor-2ttszahu2sph93rcmt9a3h.streamlit.app/`。
- 本轮阶段状态为 **Complete**。实现、本地质量门禁、提交、push、云端重启、新 Demo 在线分析和报告下载均有实际证据，可以进入下一阶段或赛事交付；开始任何后续变更前仍应重新读取实时仓库状态。
