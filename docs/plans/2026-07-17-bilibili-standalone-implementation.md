# 「每日新中国b站」独立专版实施计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

> Language: 中文

**Goal:** 从当天已审核新闻生成一条真正不同于旧竖版简报的16:9单主题B站专版，配套封面、manifest、离线核验和用户确认门。

**Architecture:** 新仓库只读 `/mnt/e/每日新中国/<date>/`，所有新产物写入本仓库 `artifacts/<date>/`。底层媒体使用现有 Pillow、edge-tts 和 FFmpeg；真实投稿未来调用既有 `sau bilibili`，阶段一只打印命令。

**Tech Stack:** Python 3.12 标准库、Pillow、requests、edge-tts、FFmpeg/ffprobe、unittest。

---

## Task 1：内容合同和解析器

- 创建 `content/2026-07-17-shield-machine.json`
- 创建 `tests/test_pipeline.py`
- 先写失败测试：源文件路径、5段脚本、前5秒钩子、时长目标、状态上限
- 实现 `bilibili_daily.py` 的加载和校验

## Task 2：横版图片、字幕与封面

- 先写失败测试：1920×1080、字幕安全区、封面文字不会溢出
- 实现本地横版画面合成与封面渲染
- 不加新依赖

## Task 3：音频与视频

- 先写失败测试：manifest 状态和哈希字段
- 调用 edge-tts 生成5段真实音频
- 优先复用当天已生成的 GPT 新闻图；不足时允许只为本样本调用现有 9router 图片端点
- FFmpeg 生成5个段落并拼成最终 MP4

## Task 4：发布预览与 fail-closed

- 先写失败测试：未到 `awaiting_user_confirmation` 或缺封面时禁止生成命令
- 只打印 `sau bilibili upload-video` 命令
- 阶段一不得执行 subprocess 投稿

## Task 5：完整验证与审查

- 运行完整 unittest
- ffprobe 验证1920×1080、2–4分钟、H.264/AAC
- 验证新旧 MP4 SHA-256 不同
- 验证旧脚本和旧视频哈希未变
- 抽帧与封面做视觉核验
- 规格审查后再做代码质量审查
- 提交 Git；不推送远端
