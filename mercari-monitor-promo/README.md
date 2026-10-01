# 煤炉助手 - 抖音推广视频

基于 Remotion 4 的抖音竖版推广视频，含配音、BGM、烧录字幕。

## 视频信息

- 分辨率：1080×1920（抖音竖版）
- 帧率：30fps
- 总时长：约 21.4s
- 场景数：6
- 配音：Edge TTS (zh-CN-YunxiNeural)
- BGM：Python 合成 120BPM 电子乐

## 场景结构

| # | 场景 | 时长 | 核心内容 |
|---|------|------|----------|
| 1 | 痛点钩子 | 3.97s | "煤炉好货秒没！" + 粉色粒子 |
| 2 | 问题展开 | 3.81s | 手动刷新→被抢→加价买 |
| 3 | 方案展示 | 3.75s | 煤炉助手 9平台·0.3秒 |
| 4 | 效果对比 | 3.44s | 30s → 0.3s 速度提升100倍 |
| 5 | 功能覆盖 | 3.14s | 监控/代购/代拍/订单/推送/多端 |
| 6 | CTA | 3.55s | GitHub 地址 + Star |

## 配色方案：二次元赛博朋克

```
背景 #0a0a1a    表面 #12122a    卡片 #1a1a3e    边框 #2a2a5e
粉色 #ff6b9d    品紫 #c44dff    青色 #00e5ff    橙色 #ff9100
荧光绿 #76ff03  金色 #ffd740    文字 #f0f0ff    灰色 #8888aa
```

## 快速开始

```bash
# 安装依赖
npm install

# 启动预览
npm start
# 浏览器打开 http://localhost:3000

# 渲染 MP4
npm run build
# 输出到 out/video.mp4
```

## 重新生成配音

```bash
python gen_voiceover.py
```

需要 `edge-tts`（`pip install edge-tts`）。

## 重新生成 BGM

```bash
python gen_bgm.py
```

需要 FFmpeg（`winget install FFmpeg`）。

## 文件结构

```
mercari-monitor-promo/
├── src/
│   ├── index.tsx          # Remotion 入口，注册 Composition
│   └── PromoVideo.tsx     # 6 场景视频组件 + 字幕 + 配音 + BGM
├── public/
│   ├── voiceover.mp3      # Edge TTS 配音
│   ├── voiceover.srt      # 配音时间轴
│   └── bgm.mp3            # 合成 BGM
├── subtitles.srt          # 视频字幕（与配音同步）
├── gen_voiceover.py       # 配音生成脚本
├── gen_bgm.py             # BGM 生成脚本
├── remotion.config.ts     # Remotion 配置
├── tsconfig.json
└── package.json
```

## 发布指引

1. `npm run build` 渲染 MP4
2. 打开抖音 → 点「+」→ 选「上传视频」
3. 选择 `out/video.mp4`（字幕已烧录）
4. 标题：**煤炉好货秒没？0.3秒监控神器！**（≤20字，前7字抓人）
5. 配文：9大日淘平台实时监控，Turbo全量Feed加速，一键代购代拍，GitHub开源免费
6. 标签：#煤炉 #日淘 #代购 #Mercari #海淘 #开源