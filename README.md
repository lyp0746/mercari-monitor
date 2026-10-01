# 煤炉助手 — 多平台日淘代购监控系统

**9大平台 · Turbo全量Feed加速 · 一键代购/代拍 · 订单全流程管理 · 双端支持(Web+桌面) · Telegram/Discord推送**

## 支持平台

| 平台 | 标识 | 地区 | 类型 | 代购/代拍 | 稳定性 |
|------|------|------|------|-----------|--------|
| Mercari | mercari_jp | 🇯🇵 日本 | 二手C2C | ✅ 代购 | 🟢 稳定 |
| Yahoo! Auctions | yahoo_auctions | 🇯🇵 日本 | 拍卖C2C | ✅ 代拍 | 🟢 稳定 |
| 駿河屋 | surugaya | 🇯🇵 日本 | 动漫/中古 | ✅ 代购 | 🟢 稳定 |
| 楽天市場 | rakuten | 🇯🇵 日本 | 新品B2C | ✅ 代购 | 🟢 稳定 |
| Yahoo!ショッピング | yahoo_shopping | 🇯🇵 日本 | 新品B2C | ✅ 代购 | 🟢 稳定 |
| PayPay フリマ | paypay_fleamarket | 🇯🇵 日本 | 二手C2C | ✅ 代购 | 🟡 不稳定 |
| Fril (Rakuma) | fril | 🇯🇵 日本 | 二手C2C | ✅ 代购 | 🟡 不稳定 |
| Bunjang | bunjang | 🇰🇷 韩国 | 二手C2C | ✅ 代购 | 🟢 稳定 |
| Carousell | carousell | 🌏 SG/HK/TW/MY/PH/AU | 二手C2C | ✅ 代购 | 🔴 较慢 |

## 核心功能

### 实时监控
- 轮询间隔 0.3-60s 可调，默认 0.3s
- Mercari 平台 Turbo 模式：**全量新品 Feed 持续拉取 + 增量ID比对 + 本地标题匹配 + 即时派发**，绕过搜索引擎索引延迟（已验证冷门词 Canon 可 8s 命中，远超关键词 API 的 100s+）
- Mercari 分类 Feed 加速：关键词可绑定分类，额外拉取分类新品流（热门分类 5~15s 命中）
- Mercari 关注卖家 Feed：卖家上新秒级可见，独立高频通道
- 多关键词并发请求，即时推送
- 连续失败自动退避，避免资源浪费
- 代理 IP 池轮换，降低被封风险

### 一键代购/代拍 ⭐新功能
- 点击商品卡片查看详情，展示完整商品信息和费用明细
- **一键代购**：普通商品直接下单，自动计算服务费、国内运费、预估总价
- **一键代拍**：雅虎拍卖商品专用，支持拍卖出价
- 费用明细透明：商品价格 → 服务费(8%) → 日本国内运费(¥60) → 国际运费(到仓计算) → 预估总计
- 自动汇率换算，8种货币实时转换

### 订单全流程管理 ⭐新功能
- 完整订单状态流转：待确认 → 已确认 → 代购中 → 已购买 → 国内发货 → 已到仓 → 国际物流 → 已签收
- 订单列表支持按状态筛选
- 每个订单包含商品信息、费用明细、状态追踪
- 支持订单状态推进和取消

### 平台账号管理 ⭐新功能
- 管理各平台登录凭证（Cookie/Token）
- 支持6大平台账号配置
- 为自动下单提供账号基础
- 账号信息加密存储

### 推送通知
- **Telegram** — Bot 消息推送 + 命令交互
- **Discord** — Webhook Embed 格式推送
- 推送内容：商品图片、标题、价格、人民币换算、成色、链接、延迟时间

### Telegram Bot 命令
```
/help              — 查看所有命令
/status            — 查看监控状态
/add canon         — 添加关键词
/bseller 12345     — 屏蔽卖家
/watch 12345       — 关注卖家
/keywords          — 列出关键词
/blacklist         — 查看黑名单
```

### 智能筛选
- 价格区间过滤、成色多选、商城过滤
- 卖家黑名单、关键词黑名单
- 降价提醒、拍卖结束提醒
- 关注卖家/商品优先推送
- 8 种货币自动汇率换算

### 双端界面
- **桌面端** — tkinter GUI，双击 EXE 即用
- **网页端** — React 现代化界面，响应式设计，挖煤姬风格粉色主题
- **无头模式** — 命令行部署，服务器专用

### 配置系统
- 所有参数通过 `config.json` 持久化
- GUI/Web 双端设置实时同步
- 同时写入 SQLite 保持兼容
- 平台独立轮询间隔配置

## 快速开始

### Windows 用户

1. 双击 `环境检查.bat` 检测环境
2. 双击 `一键启动.bat` 启动服务
3. 浏览器打开 http://localhost:5173

### 安装依赖

```bash
# 安装 uv 包管理器
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 安装项目依赖
uv sync
```

### 启动方式

```bash
# 桌面端
uv run python run_desktop.py

# Web 端一键启动
uv run python run_web.py

# 或分别启动前后端
uv run uvicorn src.api.main:app --reload --port 8000   # 后端
cd web && npm install && npm run dev                     # 前端
```

```bash
# 无头模式（服务器）
uv run python src/main.py --headless -k "关键词@平台"
```

## 默认账号

- 用户名：`admin`
- 密码：`admin123`

## 代购/代拍使用流程

1. 在首页或发现页浏览监控到的商品
2. 点击商品卡片打开详情弹窗
3. 查看费用明细（商品价、服务费、运费、预估总计）
4. 点击「🛒 一键代购」或「🔨 一键代拍」
5. 在「📦 订单」页面查看和管理订单
6. 推进订单状态：待确认 → 代购中 → 已购买 → 发货 → 签收

## 订单状态流转

```
待确认 → 已确认 → 代购中 → 已购买 → 日本国内已发货 → 已到仓库 → 国际物流中 → 已签收
  ↓         ↓         ↓         ↓           ↓              ↓
取消      取消      取消      取消        取消           取消
```

## 费用计算

| 项目 | 说明 |
|------|------|
| 商品价格 | 原价 × 实时汇率 |
| 服务费 | 商品人民币价 × 8% |
| 日本国内运费 | ¥60（预估） |
| 国际运费 | 到仓后按实际计算 |
| **预估总计** | 以上合计 |

## Telegram 配置

1. Telegram 找 @BotFather 创建 Bot，获取 Token
2. 找 @userinfobot 获取 Chat ID
3. 设置页面填入 Token 和 Chat ID
4. 点击"测试发送"验证

## Discord 配置

1. 频道设置 → 整合 → Webhooks → 新建 Webhook
2. 复制 Webhook URL
3. 设置页面粘贴 URL
4. 点击"测试发送"验证

## 打包发布

```bash
# 打包桌面端 EXE
uv run python build.py --desktop

# 打包 Web 前端
uv run python build.py --web

# 全部打包
uv run python build.py --all

# 清理缓存
uv run python build.py --clean
```

输出位置：
- 桌面端：`dist/二手监控助手.exe`
- Web 端：`dist/web/`

## 项目结构

```
mercari-monitor/
├── src/
│   ├── config.py                 # JSON配置系统
│   ├── database.py               # SQLite数据库（含订单/账号表）
│   ├── notifier.py               # 通知推送系统
│   ├── telegram_bot_service.py   # Bot轮询服务
│   ├── main.py                   # 主入口
│   ├── api/
│   │   ├── main.py               # FastAPI应用
│   │   ├── deps.py               # 依赖注入
│   │   └── routes/               # API路由
│   │       ├── auth.py           # 认证
│   │       ├── keywords.py       # 关键词管理
│   │       ├── items.py          # 商品查询
│   │       ├── item_detail.py    # 商品详情+费用计算
│   │       ├── orders.py         # 订单管理
│   │       ├── accounts.py       # 平台账号管理
│   │       ├── settings.py       # 设置管理
│   │       ├── monitor.py        # 监控控制
│   │       ├── watchlist.py      # 关注列表
│   │       ├── blocked.py        # 黑名单
│   │       └── telegram_bot.py   # Bot API
│   ├── gui/
│   │   ├── app.py                # 桌面端主界面
│   │   ├── styles.py             # 样式系统
│   │   └── widgets.py            # UI组件
│   └── monitors/
│       ├── base.py               # 监控基类
│       ├── mercari.py            # Mercari
│       ├── yahoo_auctions.py     # Yahoo拍卖
│       ├── paypay.py             # PayPay
│       ├── fril.py               # Fril/Rakuma
│       ├── bunjang.py            # Bunjang
│       └── carousell.py          # Carousell
├── web/src/                      # React前端
│   ├── api/                      # API客户端
│   ├── components/               # 通用组件
│   │   ├── ItemCard.tsx          # 商品卡片
│   │   ├── ItemDetailModal.tsx   # 商品详情弹窗
│   │   └── LogPanel.tsx          # 日志面板
│   ├── pages/                    # 页面
│   │   ├── Dashboard.tsx         # 首页
│   │   ├── Items.tsx             # 发现页
│   │   ├── Keywords.tsx          # 监控任务
│   │   ├── Orders.tsx            # 订单管理
│   │   ├── PlatformAccounts.tsx  # 平台账号
│   │   ├── Watchlist.tsx         # 收藏
│   │   ├── Settings.tsx          # 设置
│   │   ├── Stats.tsx             # 统计
│   │   ├── Logs.tsx              # 日志
│   │   ├── BlockedItems.tsx      # 屏蔽列表
│   │   └── Login.tsx             # 登录
│   ├── hooks/                    # 自定义Hooks
│   ├── styles/                   # 样式（粉色主题）
│   └── utils/                    # 工具函数
├── config.json                   # 运行时配置（自动生成）
├── run_desktop.py                # 桌面端启动
├── run_web.py                    # Web端启动
├── build.py                      # 打包工具
├── 一键启动.bat                   # Windows一键启动
├── 环境检查.bat                   # 环境检测
└── 打包发布.bat                   # 一键打包
```

## 性能参数

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| 全局轮询间隔 | 0.3s | 0.3-60s | 每个关键词的检测频率 |
| Mercari 间隔 | 0.3s | - | 平台默认间隔（含 Turbo 加速） |
| Yahoo 拍卖间隔 | 2.0s | - | 平台默认间隔 |
| PayPay 间隔 | 5.0s | - | 平台默认间隔 |
| Fril 间隔 | 2.0s | - | 平台默认间隔 |
| Bunjang 间隔 | 2.0s | - | 平台默认间隔 |
| Carousell 间隔 | 30.0s | - | 平台默认间隔 |
| API 超时 | 1.2s | - | 单次请求最大等待 |
| 连接超时 | 0.5s | - | TCP连接超时 |
| Turbo Feed 间隔 | 0.3s | config.json `turbo_interval` | Mercari 全量 Feed 拉取频率 |
| Turbo 并发池数 | 2 | config.json `turbo_concurrency` | 并发拉取 Feed 池数 |
| Turbo 分页深度 | 3 | config.json `turbo_pages` | 每池 pageToken 追页数（覆盖 +45%） |
| 分类 Feed 间隔 | 3.0s | config.json `category_interval` | Mercari 分类 Feed 拉取频率 |
| 卖家 Feed 间隔 | 2.0s | config.json `seller_interval` | 关注卖家 Feed 拉取频率 |
| Turbo 旧品阈值 | 600s | config.json `turbo_max_age` | 超过该秒数的旧品跳过，防首次运行刷屏 |
| 服务费率 | 8% | - | 代购服务费比例 |
| 国内运费 | ¥60 | - | 日本国内运费（预估） |

## 常见问题

**Q: 首次启动报错？**
```bash
# Windows
rmdir /S /Q .venv __pycache__
# 然后重新 uv sync
```

**Q: 重置密码？**
删除数据库重启即可：
```bash
del data\monitor.db
```

**Q: 监控速度慢？**
1. Mercari 平台 Turbo 模式已自动加速（全量Feed 8~25s 命中），无需额外配置
2. 关键词绑定分类（监控任务 → 高级 → 煤炉分类加速），热门分类可进一步提前到 5~15s
3. 配置代理 IP 池提升稳定性
4. 减少关键词数量降低负载
5. 开启商城过滤减少无效推送

**Q: 如何代购/代拍？**
1. 点击商品卡片打开详情
2. 查看费用明细
3. 点击「一键代购」或「一键代拍」
4. 在订单页面管理订单状态

**Q: Telegram Bot 不工作？**
1. 确认 Token 和 Chat ID 填写正确
2. 点击"测试发送"验证
3. 启动监控后 Bot 自动激活
4. 发送 `/help` 测试

## 技术栈

- Python 3.11+
- httpx (异步客户端)
- curl_cffi (反反爬)
- FastAPI + Uvicorn (Web 后端)
- React + TypeScript + Vite (Web 前端)
- tkinter (桌面端)
- SQLite (数据存储)
- PyInstaller (打包)