# AGENTS.md — AI 代理最小作业卡

你面对的是一个「只追加」的视频提示词库。唯一数据源：`视频提示词库-多模型.html`（`script#data` 条目数组 + `script#meta` 规则与指纹）。完整手册见 `README.md`（冲突以 README 为准；深度规格见 `提示词库说明.md`）。

## 不可破的约束

1. 只追加，不删改老条目；不改文件名，不 bump 版本。
2. `original` 逐字不可变（SHA-256 指纹校验）。
3. 一切写入只能通过 `python 追加提示词.py "视频提示词库-多模型.html" 新条目.json`；禁止手改 data/meta 块。
4. 仓库 `main` = 唯一真源，git 历史即备份；改前拉最新，改后立刻推回并回读校验。
5. 严禁把 token / 密钥写入任何提交文件。

## 标准作业

1. 把拿到的提示词整理成 9 字段 JSON 数组：`model`（系列+空格+版本）/ `cat` / `sub` / `name`（中文）/ `desc`（中文）/ `tags`（数组 3–6 个）/ `lang` / `original`（逐字保留）/ `src`；外文条目另加 `zh` 中文译文。
2. 分类优先复用 README §4 的现有 cat/sub；新建子类用「X·Y」式。
3. 能跑 Python：拉最新库 → 追加 → `python 库维护工具.py verify` 全绿 → 推送 main（提交信息 `追加 N 条：<简述>`）→ 回读远端再 verify。
4. 跑不了 Python：把 JSON 提交到 `待入库/`，CI 自动入库，Actions 绿勾为准。
5. 校验红灯 = 零写入：修 JSON 重来；已推坏就 `git revert`，不要 force push。
