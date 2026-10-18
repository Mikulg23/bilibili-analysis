# B 站视频数据分析与 AI 知识库

本项目对应“大数据开发综合实践”中的“基于多技术栈的数据分析与 AI 知识库构建”实训，围绕 B 站视频数据完成采集、清洗、分布式存储、统计分析、数据挖掘和 Web 可视化。AI 知识库问答为选做模块。

**当前状态：已完成深色后台前端、模块一数据采集与模块二数据预处理。** 清洗模块支持本地 CSV、本机 MySQL 和虚拟机 HDFS 存储；统计分析、数据挖掘、真实管理员鉴权及 AI 问答尚未实现。页面不会生成演示数据或模拟业务成功。

## 本地预览

项目代码使用 Git 管理。`.env`、虚拟环境、原始/清洗数据、模型、日志及 Python 缓存不提交；空数据目录通过 `.gitkeep` 保留。提交作者默认使用占位信息，不包含个人姓名或邮箱；后续上传 GitHub 时再配置目标仓库。

本地已使用 Python 3.11 创建 `.venv`。VS Code 工作区已配置该解释器；若之前已手动选过其他环境，请执行 `Python: Select Interpreter`，选择本项目 `.venv/Scripts/python.exe`，然后新建终端。

在本项目目录中运行：

```shell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

访问 `http://127.0.0.1:5002/login`，点击“预览管理界面”进入工作台，也可以直接访问 `http://127.0.0.1:5002/dashboard`。根路径 `/` 自动跳转至登录页。在启动终端按 `Ctrl+C` 停止服务。

也可先执行 `.\.venv\Scripts\Activate.ps1`，再使用 `python app.py`。若 PowerShell 阻止激活脚本，直接使用上面的解释器完整路径即可，无需修改系统执行策略。环境需要重建时，先执行 `py -3.11 -m venv .venv`，再安装依赖。

- 当前没有可用账号，不应输入真实密码；登录表单请求预留接口后会提示“登录服务尚未接入”。
- `/dashboard` 当前公开用于本地预览，**没有访问保护**；服务只监听本机回环地址，不作为生产服务部署。
- 采用 HTML、CSS、原生 JavaScript，无前端编译步骤。ECharts 5.6.0 通过固定版本 CDN 加载，需要网络；加载失败时显示提示，其余界面仍可使用。
- 默认日期为浏览器本地日期的前一天。先填写关键词，再执行相应模块操作；日期和关键词变化会清空旧结果，旧请求返回后也不会覆盖新范围。
- 数据采集、预处理已接入实际接口，其余未实现接口的 404/405 仍显示“接口尚未接入”。采集期间锁定日期、关键词及采集按钮；执行预处理前先停止采集。

## 模块一 数据采集

### 从页面运行

1. 使用项目虚拟环境运行 `app.py`，从登录页点击“预览管理界面”。
2. 打开“数据采集”，填写关键词、采集日期和页数（1–100）。**日期是采集批次标签，不是视频发布日期筛选。** 顶部默认仍是昨天，实际运行前请选择要记录的采集日期。
3. 点击“开始采集”，Chrome 默认在后台无头运行，不弹出窗口。首次使用时 Selenium 会自动查找浏览器并下载匹配驱动，需要网络；也可在 `.env` 中指定路径。
4. 页面每两秒查询当前任务状态，展示进度、失败数量、CSV 文件名和前 20 条预览。完整数据保存在 `data/raw/`。

当前一次只允许一个任务。刷新页面可继续查看同一个服务进程中的任务；“查看当前任务”会切回该任务的日期和关键词。点击“停止采集”即可结束当前任务并保留已保存的数据，**不需要关闭 Flask**；显示“已停止”后可再次开始。随机间隔和页面元素等待可被中断；若正在加载网页，需等当前请求完成或达到 `CRAWLER_WAIT_SECONDS` 超时，首次驱动下载也需等待返回。停止处理中不会接受新任务。

当前是本机采集工具，**采集接口尚无管理员登录鉴权**，只允许本机 Host 和同源 JSON 请求，请保持 `127.0.0.1` 监听，不对外部署。

### 从命令行运行

```powershell
# 先用少量数据确认环境，省略 --date 时使用当天作为采集日期。
.\.venv\Scripts\python.exe pachong.py --keyword "数据分析" --pages 1 --limit 2

# 正式采集示例，页数按实际需求填写；由使用者手动启动。
.\.venv\Scripts\python.exe pachong.py --keyword "数据分析" --pages 20 --date YYYY-MM-DD
```

将 `YYYY-MM-DD` 替换为实际采集日期。`--limit` 限制本次新增条数；默认无头运行，`--show-browser` 可显示浏览器以排查登录或人工验证，`--headless` 可显式使用无头模式。命令行采集用 `Ctrl+C` 停止。

### 数据和配置

- 文件名为 `bilibili_video_data_YYYYMMDD_关键词.csv`，使用 `utf-8-sig` 编码，字段依次为 `title`、`url`、`up`、`play`、`like`、`coin`、`favorite`、`share`，对应标题、视频链接、UP 主、播放、点赞、投币、收藏和转发。
- Selenium 先从搜索页获取视频链接，再进入详情页读取指标；保留“万”等原始单位。未读取到的数值留空，不填充为 0，交给模块二清洗。
- 同日期、同关键词再次运行时，读取已有 URL 并追加新视频，不覆盖原文件。每写入一条就刷新文件；失败或手动中断时保留已写入的数据。CSV 若被 Excel 占用，请先关闭文件。
- 默认每次访问间隔随机 2–4 秒。搜索页超时会停止；个别视频失败会跳过，连续三条失败则停止并提示。遇到登录或验证时不自动绕过，可将 `.env` 中 `CRAWLER_HEADLESS=false` 并重启服务，使用可见窗口排查。
- 2000 条是实训总目标，页数并不保证固定条数。搜索结果可能提前结束或重复，程序会如实停止；可分批、更换关键词采集，合并时还需按 URL 全局去重。
- 本模块只保存原始 CSV，**不上传 HDFS、不写 MySQL、不启动定时采集**。清洗后上传存储留给模块二；自动采集后续再接入。
- 按需将 `.env.example` 复制为 `.env`。可配置项为 `CHROME_BINARY`、`CHROMEDRIVER_PATH`（留空自动查找）、`CRAWLER_HEADLESS`、`CRAWLER_WAIT_SECONDS`、`CRAWLER_DELAY_MIN`、`CRAWLER_DELAY_MAX`。无需提供账号、密码或 Cookie。

当前采用单进程 Flask 加一个后台线程，任务状态只保存在内存；重启服务后状态清空，CSV 保留。再次按同批次运行会跳过已有视频，不是断点页码恢复。运行 `python tests/test_collection.py` 可做不联网的轻量接口自检。

## 模块二 数据预处理

### 操作方式

启动或重启 `app.py`，进入“数据预处理”，选择实际采集日期。**关键词留空时，合并该日期所有原始 CSV 并跨文件去重；填写关键词则只处理对应文件。** 点击“执行数据预处理”，查看前后数量、重复数量、填补与截尾统计及两项存储状态。

也可以在项目目录执行：

```powershell
# 合并该采集日期所有关键词；本项目现有原始批次是 2026-10-16。
.\.venv\Scripts\python.exe preprocessing.py --date 2026-10-16

# 只清洗一个关键词。
.\.venv\Scripts\python.exe preprocessing.py --date 2026-10-16 --keyword "数据分析"
```

### 固定清洗规则

1. 读取八个规定字段。数字缺失、负数或无法识别的数值填 0；缺失标题和 UP 主分别填“未命名视频”“未知UP主”。
2. 将千、万、亿等单位转换成纯数字，支持逗号分隔与全角字符，最终存为非负整数。
3. 标题去除 HTML 标记、控制字符与多余空白，保留正常中文、符号及表情。
4. URL 统一为标准 B 站 BV 视频链接，移除无效 URL；去除查询参数后按 URL 保留首条记录。合并处理时同时去除跨文件重复。
5. 对去重后的五个数值字段计算 IQR，超出 `Q1 - 1.5×IQR` 到 `Q3 + 1.5×IQR` 的值截到非负边界；**不因异常值删除视频行**。IQR 为 0 时不截尾，避免把少数非零样本全部压成 0。原始真实数值仍保留在 raw 目录。

清洗后的记录数为原始数减去无效链接数和重复数；IQR 统计的是调整的单元格数，并非删除的视频数。清洗会改变高热度视频的指标，后续分析基于处理后的数据；需要原始指标时读取原始 CSV。

### 输出与存储

- 本地输出到 `data/processed/`，使用 UTF-8 BOM CSV。先写临时文件再替换，**不修改任何原始 CSV**；清洗为空时不会覆盖已有结果。
- 单关键词文件、MySQL 表按 `bilibili_video_data_YYYYMMDD_关键词` 命名。日期全部关键词的合并结果使用后缀 `all`；特殊字符、超长关键词或保留后缀冲突会使用安全名称与短摘要，避免 SQL 注入和名称碰撞。
- `.env` 中配置 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE`。默认目标为本机数据库 `bilibili_analysis`。首次写入会执行 `sql/init.sql` 创建数据库和空的视频表模板，再创建该批次的实际表；账号需要相应建库、建表和读写权限。
- 同批次重跑时，在事务内替换该批次表的记录；插入失败回滚，保留旧数据。数据库表使用 UTF-8、URL 唯一索引和非负整数指标。连接凭据只保存在被忽略的本地 `.env`，不写进 SQL。
- HDFS 使用现有虚拟机的 WebHDFS 接口，不重新安装或格式化 Hadoop。配置项为 `HDFS_WEBHDFS_URL`（NameNode HTTP 基地址，不包含 `/webhdfs/v1`）、`HDFS_USER`、`HDFS_DATA_DIR`。按官方协议先获取 DataNode 上传地址，再上传清洗文件，最后核对文件大小：[WebHDFS 官方文档](https://hadoop.apache.org/docs/r3.3.6/hadoop-project-dist/hadoop-hdfs/WebHDFS.html)。本机需要能直达 NameNode 和 DataNode，虚拟机地址变化后更新本地配置。
- 当前 HDFS 采用实验环境的简单用户认证，不适用于启用了 Kerberos 的集群。MySQL 与 HDFS 分别反馈结果；任一写入失败时，页面显示警告，本地 CSV 保留，可修复连接后重跑，**不会假报三端均完成**。

当前已处理批次 `2026-10-16`：8 个 CSV 共 2336 条，移除 5 条重复，保留 2331 条；填补 716 个数值、截尾 1782 个数值，无无效链接。已核对 MySQL 表与 HDFS CSV 均为 2331 条，原始文件内容未改变。

预处理采用同步接口，不新增任务队列。页面为存储写入预留 60 秒；同一时间只允许一个预处理，避免重复替换文件和数据表。修改 `.env` 后需重启服务。核心自检可运行 `tests/test_preprocessing.py` 和 `tests/test_database.py`，均不连接外部服务。

## 文件结构

```text
bilibili-analysis/
├── app.py                     # Flask 主程序、路由、登录鉴权
├── config.py                  # 统一读取项目配置
├── db.py                      # MySQL 连接与数据库操作
├── scheduler.py               # 每日凌晨自动采集任务
├── pachong.py                 # Selenium 视频数据采集
├── preprocessing.py           # Pandas 数据清洗
├── spark_analysis.py          # PySpark 统计分析
├── machine_kmeans.py          # K-Means、Apriori、爆款预测
├── AI_Knowledge.py            # LangChain + Ollama 知识库问答（选做）
├── templates/
│   ├── login.html             # 登录页面
│   └── index.html             # 系统主页面
├── static/
│   ├── css/
│   │   ├── login.css          # 登录页样式
│   │   └── style.css          # 主页面样式
│   └── js/
│       ├── login.js           # 登录交互
│       ├── app.js             # 页面交互、日期选择、API 请求
│       └── charts.js          # ECharts 图表渲染
├── data/
│   ├── raw/                   # 本地原始 CSV
│   └── processed/             # 清洗后的 CSV，后续上传 HDFS
├── models/
│   ├── cluster_model.pkl      # 训练后生成，当前不存在
│   └── scaler.pkl             # 训练后生成，当前不存在
├── sql/
│   └── init.sql               # MySQL 建库、建表和用户表
├── scripts/
│   ├── init_hdfs.sh           # 初始化 HDFS 目录
│   └── run_spark.sh           # 启动 Spark 任务
├── logs/                      # 运行日志
├── tests/
│   ├── test_preprocessing.py  # 数据清洗测试
│   └── test_database.py       # 数据库操作测试
├── .env.example               # 环境变量示例，仅放占位值
├── .gitignore                 # Git 忽略规则
├── requirements.txt           # Python 依赖清单
└── README.md                  # 项目说明
```

## 技术栈约束

| 层次 | 指定技术 | 实现约束 |
| --- | --- | --- |
| 开发语言 | Python 3.8 及以上 | 实际 Python 版本需与所选依赖版本兼容；实现时在依赖清单中明确版本 |
| 数据采集 | Selenium、Chrome、ChromeDriver | ChromeDriver 与 Chrome 版本匹配；设置随机延时，避免高频请求 |
| 数据清洗 | Pandas、NumPy | 使用 Pandas 完成规定的清洗流程 |
| 分布式存储 | Hadoop 3.x、HDFS | 先清洗，再将清洗后的数据上传 HDFS |
| 结构化存储 | 本机 MySQL | 存储清洗后数据、视频聚类结果及用户信息 |
| 分布式分析 | Spark 3.x、PySpark | 从 MySQL 读取数据完成统计，不能用 Pandas 替代本模块；连接 MySQL 需配置兼容的 JDBC 驱动 |
| 机器学习 | scikit-learn、mlxtend、joblib | scikit-learn 实现 K-Means，mlxtend 实现 Apriori，joblib 保存及加载模型 |
| 后端 | Flask | 提供登录鉴权、角色权限控制和业务接口；计划监听 5002 端口 |
| 前端 | HTML、CSS、原生 JavaScript、ECharts | 页面放在 templates，静态资源放在 static，通过接口获取图表数据 |
| AI 问答（选做） | LangChain、Ollama | 基于采集数据构建本地 RAG；手册指定模型为 qwen2.5:1.5b-instruct |
| 定时任务 | scheduler.py | 实现每日凌晨自动采集；具体调度方式待实现时确定 |

支持 Windows / Linux；手册推荐在 Linux 环境完成 Hadoop 和 Spark 实验。Java、MySQL 驱动等配套组件的具体版本，应在实现时按选定的 Hadoop、Spark 版本确定。

## 数据流与存储约束

```text
Selenium 采集 → data/raw/ 原始 CSV → Pandas 清洗
                                      ↓
                           data/processed/ 清洗 CSV
                                      ├── 上传 HDFS
                                      └── 写入本机 MySQL
                                             ├── PySpark 统计 → Flask → ECharts
                                             └── K-Means / Apriori → Flask → 页面
原始 CSV → 本地 RAG 知识库 → Ollama → 问答页面（选做）
```

- 至少采集 2000 条视频，字段包括视频标题、视频 URL、UP 主、播放量、点赞数、投币数、收藏数、转发数。
- 原始数据文件按 `bilibili_video_data_年月日_关键词.csv` 命名；清洗后数据按日期及关键词写入对应的 MySQL 表，表名遵循手册约定。动态表名必须经过校验，禁止直接拼接用户输入。
- 清洗流程必须包括缺失值处理、万/千单位换算、IQR 四分位数异常值处理、标题文本清洗和 URL 去重。
- 按当前确认的流程执行：**先清洗，再上传 HDFS 并写入本机 MySQL**，同时保留本地原始和清洗 CSV；不使用虚拟机 MySQL 存储项目业务数据。

## 功能约束

### 统计分析

`spark_analysis.py` 使用 PySpark 完成以下四项分析，并返回适合 ECharts 使用的数据：

1. `top10_play(file_name)`：播放量前十，返回标题列表和播放量列表，超长标题截断。
2. `interaction_ratio(file_name)`：点赞、投币、收藏、转发总量，返回包含 `name` 和 `value` 的对象列表。
3. `title_len_play(file_name)`：按标题长度分组，统计总播放量（单位万），返回横纵坐标列表。
4. `like_coin_scatter(file_name)`：返回点赞数与投币数的二维数组。

以上函数名及参数名沿用手册；数据源为所选日期对应的 MySQL 数据，`file_name` 的具体含义需在实现时统一。

### 数据挖掘与预测

- K-Means 只允许使用播放量、点赞数、投币数、收藏数、转发数等数值特征，禁止传入标题、URL、UP 主等文本。
- 使用肘部法确定 K 值，划分视频热度类别，并将聚类结果更新到 MySQL。
- 前端支持输入特征值，使用训练完成的模型进行爆款预测；该结果是基于聚类的热度判断。
- 训练和预测必须保持特征顺序及标准化方式一致；标准化器与聚类模型分别保存为 `scaler.pkl` 和 `cluster_model.pkl`。
- Apriori 挖掘点赞、投币、收藏、转发之间的关联规则，并展示到前端；数值指标转为交易项的规则需在实现时明确。

### 权限与日期

- 区分管理员和普通用户，只有管理员可发起数据采集；权限必须在后端检查。
- 支持手动采集和每日凌晨自动采集前一天的数据；采集时需明确日期筛选口径。
- 默认展示前一天的数据，统计分析、聚类、预测和关联规则等功能支持按日期选择数据。
- 定时任务应避免重复启动导致同一批任务重复执行。

### AI 知识库（选做）

基于采集的 CSV、LangChain 和 Ollama 本地模型构建 RAG 问答，支持查询 UP 主视频数量、播放量最高的视频及高互动视频等问题。检索、嵌入和切分方案待实现时确定；回答应以所选数据为依据。

## 配置与隐私约束

- 项目配置统一由 `config.py` 读取，数据库密码、Flask 密钥等通过本地环境变量提供，不写入源码。
- `.env.example` 只提供配置项和占位值，不填写真实账号、密码、Cookie 或其他个人信息。
- `.gitignore` 已排除虚拟环境、Python 缓存和本地 `.env` 文件；后续接入业务时补充日志、采集数据和生成模型的忽略规则。
- 用户密码不得明文存储；数据库查询使用参数化方式，动态标识符单独校验。
- 日志与演示材料不记录或展示密码、Cookie、令牌等敏感信息；模型文件仅加载可信的本地生成文件。

## 后续实现与验证

建议按“环境配置与数据库 → 采集 → 清洗 → Spark 分析 → 数据挖掘 → Flask 与前端 → 定时任务 → 选做 AI 问答”的顺序实现。

`requirements.txt` 已包含 Flask、环境变量读取、MySQL 连接、Selenium、Pandas/NumPy、PySpark 3.5、K-Means/Apriori 和 APScheduler 所需的 Python 依赖，使用项目的 Python 3.11 虚拟环境安装。`PyMySQL[rsa]` 包含 MySQL 密码认证所需组件。当前暂不开发本地 AI，未加入 LangChain、Ollama 或向量库依赖。

当前已验证 Chrome/ChromeDriver、本机 MySQL 和虚拟机 HDFS 的实际读写；Spark 与 MySQL Connector/J 驱动仍需在模块三接入时核对。采集与预处理使用现有依赖，不新增 ORM、前端框架或任务队列。统计分析、挖掘、AI、定时任务等后续模块仍未实现。

验收至少覆盖：登录与角色权限、2000 条数据采集、HDFS 写入、清洗及 MySQL 写入、四类图表、聚类结果、爆款预测、关联规则、日期切换和自动采集。选做 AI 模块完成后再验证问答。报告中应提供实现说明、运行截图和测试用例，不将未验证的功能标记为完成。

## 前端预留 API

请求统一发送到同源 `/api`，POST 使用 `Content-Type: application/json`，GET 使用查询参数。响应使用 JSON：`{ "success": true, "message": "说明", "data": {} }`；业务失败设置 `success: false` 并返回 `message`。HTTP 401 表示未登录，403 表示无权限，404/405 表示当前接口尚未接入。

除登录、退出、采集状态及停止请求外，数据请求携带 `date`（`YYYY-MM-DD`）与 `keyword`。预处理允许关键词为空，表示合并该日期全部原始 CSV；其他业务仍要求关键词非空。以下列出额外请求字段及成功响应的 `data` 字段，字段名与现有前端保持一致。

| 方法与路径 | 额外请求字段 | 返回 data |
| --- | --- | --- |
| `POST /api/login` | `username`, `password`；不携带日期和关键词 | `{}`；成功后由后端设置登录会话，前端进入工作台 |
| `POST /api/logout` | 无；不携带日期和关键词 | `{}`；成功后返回登录页 |
| `POST /api/collect` | `pages`（1–100 的整数） | HTTP 202，返回采集任务状态，立即开始后台采集 |
| `GET /api/collect/status` | 不携带筛选字段 | 当前任务状态；未启动时为 `{state: "idle"}` |
| `POST /api/collect/stop` | 仅 `task_id`，不携带筛选字段 | 返回停止中的任务状态；已结束任务保持原状态 |
| `POST /api/preprocess` | 无；关键词可留空 | `before_count`, `after_count`, `removed_duplicates`, `rows`，以及清洗和存储状态 |
| `GET /api/analysis` | 无 | `summary`, `top10_play`, `interaction_ratio`, `title_len_play`, `like_coin_scatter` |
| `POST /api/mining/train` | 无 | `optimal_k`, `elbow`, `distribution`, `rows` |
| `GET /api/mining/clusters` | 无 | 同训练结果 |
| `POST /api/mining/predict` | `play`, `like`, `coin`, `favorite`, `share`（均为非负整数） | `label`（非空热度判断文字） |
| `GET /api/mining/rules` | 无 | `rules`（规则数组） |
| `POST /api/knowledge/build` | 无 | `status`（非空状态文字） |
| `POST /api/knowledge/ask` | `question`（非空文字） | `answer`（非空回答文字） |

返回数据结构约定：

- 视频记录：`{title, url, up, play, like, coin, favorite, share}`；聚类明细另加 `cluster` 和 `label`。预览记录由后端限制数量，总条数通过计数字段返回。
- `summary`：`{video_count, total_play, total_interactions, up_count}`，计数为 JSON 数字；无数据时返回 0，前端初始未加载时显示破折号。
- `top10_play`：`{titles: [], values: []}`，标题与播放量一一对应，按播放量降序排列。
- `interaction_ratio`：`[{name, value}]`，分别为点赞、投币、收藏、转发总量。
- `title_len_play`：`{x: [], y: []}`，横轴标题长度，纵轴总播放量（万）。
- `like_coin_scatter`：`[[点赞数, 投币数]]`。
- `elbow`：`{k: [], sse: []}`；`distribution`：`[{name, value}]`，表示各热度类别及视频数量。
- `rules`：`[{antecedents: [], consequents: [], support, confidence, lift}]`；支持度与置信度使用 0–1 数值，提升度使用数值，页面展示原始值。

采集任务数据包含 `task_id`、`state`（`running` / `stopping` / `stopped` / `completed` / `error`）、`date`、`keyword`、`page`、`pages`、`count`（文件累计条数）、`new_count`、`failed_count`、`filename`、`rows`（最多 20 条）和 `message`。状态查询没有筛选参数，返回本进程当前任务。已有任务运行或正在停止时重复启动返回 HTTP 409；停止请求必须匹配当前任务编号，避免停止错误的任务。

列表无数据时返回空数组，图表坐标无数据时返回两个空数组，不使用虚构记录填充。采集已使用任务状态查询，其余接口仍按一次请求返回最终结果预留，普通请求超时为 20 秒；后续训练与知识库任务接入时再决定其耗时处理方式。

预处理额外返回 `source_files`、`invalid_urls`、`filled_numeric_cells`、`clipped_outlier_cells`、`filename`、`table_name`、`mysql_status`、`hdfs_status` 和 `storage_complete`。本地清洗成功但外部存储未完成时仍返回清洗结果，并将 `storage_complete` 设为 `false`，前端使用警告样式；预处理请求超时单独设为 60 秒。

所有鉴权与管理员权限必须在后端补齐。前端没有保存密码、令牌或模拟登录状态；返回文字使用文本方式展示，不执行接口返回的 HTML。
