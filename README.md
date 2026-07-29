# iCloud HME — 多账号聚合管理平台

基于 iCloud Hide My Email 协议，批量创建 `@icloud.com` 隐私邮箱的商用聚合平台。

- 👥 **多账号管理** — 同时管理多组 iCloud 账号，每个独立存储、独立会话
- 🔗 **账号-别名映射** — 自动提取真实 Apple ID，每个隐私邮箱标注归属账号
- ⏱ **定时调度** — 北京时间 07:00–20:00 运行，60–90 分钟随机触发
- 🌐 **Web UI** — 现代化仪表盘 + 账号管理 + 别名管理 + 跨账号批量创建

## 前提条件

- **iCloud+ 订阅**（Hide My Email 需要 iCloud+）
- Python 3.10+
- Windows / macOS / Linux

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动 Web UI
python web_ui.py

# 3. 打开 http://127.0.0.1:5050
#    点击左下角「导入 Cookie」添加第一个账号
#    支持粘贴 Cookie Editor 的 Header String 或 JSON
```

## 使用方式

### Web UI（推荐）

```bash
python web_ui.py                    # 启动 Web 界面
python web_ui.py --port 8080        # 指定端口
python web_ui.py --scheduler        # 启动时自动开启调度器
```

界面功能：

| 模块 | 功能 |
|------|------|
| **账号管理** | 添加/切换/删除账号，每个账号独立 Cookie + 会话 |
| **仪表盘** | 账号总数、总别名数、今日创建数，每账号一张状态卡片 |
| **别名列表** | 实时拉取所有别名，支持复制、停用和删除 |
| **批量创建** | 勾选目标账号 → 输入数量 → 跨账号轮询创建 |
| **调度器** | Web/CLI 共用同一核心，北京时间窗口内随机轮询活跃账号 |

### 命令行调度器

```bash
# 多账号定时调度（需要先通过 Web UI 添加账号）
python scheduler.py

# 后台守护进程
python scheduler.py -d
```

### CLI 手动操作

```bash
# 列出所有别名
python icloud_hme.py list --cookies cookies.json

# 创建别名
python icloud_hme.py create -n 5 --cookies cookies.json

# 删除别名
python icloud_hme.py delete --email xxx@icloud.com --cookies cookies.json
```

## Cookie 获取

| 方式 | 说明 |
|------|------|
| Web UI 导入 | 点击左下角按钮，粘贴 Cookie Editor 的 Header String |
| Chrome 扩展自动提取 | 在 `chrome://extensions` 加载项目内 `icloud-cookie-extensions`，然后在更新 Cookie 弹窗点击自动提取 |
| 命令行 `--cookies` | 指定 JSON 文件路径 |

支持两种输入格式：
- **Header String**：`name1=value1; name2=value2; ...`
- **JSON**：`{"name1":"value1", "name2":"value2"}`

导入后自动持久化到 `accounts.json`，重启无需重新粘贴。

## 调度逻辑

```
北京时间 07:00–20:00 运行
  → 每轮遍历所有活跃账号
  → 每个账号随机创建 3–5 个
  → 单个别名间隔 15–45 秒，账号间隔 2–5 分钟
  → 全部完成后随机等待 60–90 分钟
  → Web UI 与 scheduler.py 共用同一调度核心
```

## 文件结构

```
├── icloud_hme.py        # 核心库：Cookie 提取 / HME API / 账号身份提取
├── account_manager.py   # 多账号管理器：CRUD / 批量创建 / 别名索引
├── web_ui.py            # Flask Web 面板 + 内置调度器
├── icloud-cookie-extensions/ # Chrome Cookie API 本地桥接扩展
├── scheduler.py         # 独立命令行调度器
└── requirements.txt     # pip 依赖
```

运行时生成：

```
accounts.json          # 所有账号及 Cookie（自动持久化）
scheduler_state.json   # 调度器历史状态
logs/                  # 运行日志
results/               # 创建的邮箱列表
```

## 依赖

```
requests>=2.25          # HTTP
pycryptodome>=3.15     # Chrome cookie 解密 (Windows)
pywin32>=305           # Windows DPAPI (仅 Windows)
flask>=3.0             # Web UI
```

## License

MIT