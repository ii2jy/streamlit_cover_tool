# 小红书内容与封面工作台

一个本地运行的 Streamlit 工具，把情报收集、灵感排期、封面生成和历史素材拆解串成同一条工作流。四个模块共享 SQLite 数据库，以及统一的钩子结构和版式分类标准。

## 四个模块

1. **情报雷达**：粘贴热点、话题、产品或市场信息，由 AI 总结核心、提炼普通人可承接机会并判断相关度；结果可一键转为灵感。
2. **灵感库**：快速记录选题，使用 AI 匹配已有钩子结构，设置状态与发布日期，再携带主题和钩子进入生成器。
3. **封面生成器**：上传新照片，结合主题、指定钩子和最近 10 条历史素材生成 3 套方案；自动合成初版 PNG，可选择、下载，并把关联灵感标记为已发布。
4. **素材库**：上传对标封面与原标题，使用视觉模型拆解版式、钩子、配色、字体、情绪与停留原因。

素材库和生成结果共用 3:4 图片网格。桌面端固定三列，大屏内容区保持紧凑，手机端自动纵向排列；完整信息放在详情弹窗内。

## 项目结构

```text
streamlit_cover_tool/
├─ app.py                 # 应用入口、导航、素材库和封面生成器
├─ database.py            # SQLite 建表、迁移、分类预置和索引
├─ radar.py               # 情报雷达：AI 分析、筛选、转灵感
├─ ideas.py               # 灵感库：录入、AI 分类、排期、状态与跳转
├─ grid_component.py      # 可复用 3:4 图片网格与详情弹窗
├─ cover_renderer.py      # Pillow 初版封面合成模板
├─ prompts.py             # 素材拆解与标题生成共用的固定设计原则
├─ ui_styles.py           # 全局浅色卡片视觉样式
├─ requirements.txt       # Python 依赖
├─ .streamlit/
│  └─ secrets.toml.example
├─ data/
│  ├─ covers.db           # 本地 SQLite 数据库
│  └─ images/             # 素材库原始图片
└─ tests/                 # 数据库、AI Schema、渲染和 UI 回归测试
```

## 数据库

- `signals`：情报原文、AI 总结、机会建议、相关度和标签。
- `ideas`：灵感、来源信号、钩子外键、状态和发布日期。
- `cover_samples`：素材原图、原标题和完整拆解。
- `hook_types`：四个模块共用的钩子结构类型。
- `layout_types`：素材库和生成器共用的版式类型。
- `schema_migrations`：数据库升级记录。

AI 新建分类时会写入分类库并标为 `pending`，页面显示“新增待审核”。旧素材中的文字分类字段仍然保留，升级不会删除历史记录。

素材拆解和标题生成每次都会把 `prompts.py` 中的“0.5秒停留机制”作为 Responses API 的系统级 `instructions` 注入。具体图片、标题、主题和历史参考仍放在用户级任务 prompt 中，确保固定原则始终拥有更高优先级。

## Windows 本地运行

第一次运行：

```powershell
cd D:\onedrive\文档\ChatGPT\封面图\streamlit_cover_tool
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

推荐把 `.streamlit/secrets.toml.example` 复制为 `.streamlit/secrets.toml`，写入：

```toml
OPENAI_API_KEY = "你的_OpenAI_API_Key"
```

也可以只在当前 PowerShell 窗口设置：

```powershell
$env:OPENAI_API_KEY="你的_OpenAI_API_Key"
$env:OPENAI_MODEL="gpt-4o"
```

启动应用：

```powershell
python -m streamlit run app.py
```

浏览器通常自动打开 `http://localhost:8501`。停止程序时回到 PowerShell，按 `Ctrl + C`。

## 运行测试

```powershell
python -m unittest discover -s tests -v
```

API Key、数据库和用户图片都只保存在本机；不要把 `.streamlit/secrets.toml`、`data/covers.db` 或私人素材提交到公开 GitHub 仓库。
