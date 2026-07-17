# 每日新中国b站

> Language: 中文

独立的 B站专版视频制作与发布管理仓库。

## 当前阶段

阶段一只生成一条离线样本，不自动公开投稿：

- 日期：2026-07-17
- 主题：国产14米级超大直径盾构机“先锋号”下线
- 视频：1920×1080、16:9、2–4分钟、单主题解释型内容
- 封面：1920×1080、单一主体、金色高对比大字
- 状态上限：`awaiting_user_confirmation`

## 不变量

- 只读 `/mnt/e/每日新中国/<date>/` 下的审核材料。
- 不修改旧《每日新中国》生成和跨平台发布流程。
- 不复用旧流程最终 MP4。
- 未经用户确认，不执行 `sau bilibili upload-video`。
- 本仓库使用现有 Python、Pillow、requests、edge-tts、FFmpeg，不安装新依赖。

## 计划中的命令

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_sample.py --date 2026-07-17
python3 scripts/verify_sample.py --date 2026-07-17
python3 scripts/preview_publish.py --date 2026-07-17
```

最后一条永远不执行投稿。当前本机 `sau bilibili` 尚未暴露
`--thumbnail`，因此会以 `BLOCKED` 非零退出；用户确认样本并补齐运输层后，
它才只打印带封面的目标投稿命令。
