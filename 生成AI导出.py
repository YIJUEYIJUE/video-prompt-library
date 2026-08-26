#!/usr/bin/env python3
"""生成 AI 静态导出文件（供 AI 直接读取，无需浏览器）

输出两份：
1. AI导读索引.md —— 轻量版（~75K 字符 ≈ 2.5 万 token）：分类体系 + 每条一行摘要
   AI 一次读完即可了解库里有什么、在哪。
2. AI-全库.jsonl —— 全量版（每行一条 JSON，含原文）：入向量库用，
   或 AI 按需 grep/分段读取。

CI 在每次入库后自动重跑本脚本，两文件与库保持同步。
"""
import re, json, sys, os
from collections import Counter

HTML = sys.argv[1] if len(sys.argv) > 1 else '视频提示词库-多模型.html'
h = open(HTML, encoding='utf-8').read()

blocks = {}
for tag in ('data', 'general', 'tutorials'):
    m = re.search(r'<script id="%s"[^>]*>\n?(.*?)\n?</script>' % tag, h, re.S)
    if m:
        blocks[tag] = json.loads(m.group(1))
mm = re.search(r'<script id="meta"[^>]*>\n?(.*?)\n?</script>', h, re.S)
meta = json.loads(mm.group(1)) if mm else {}

data, gen, tut = blocks['data'], blocks['general'], blocks['tutorials']

# ---------- AI导读索引.md ----------
out = []
out.append('# 视频提示词库 · AI 导读索引（轻量版）')
out.append('')
out.append('> 本文件供 AI 快速了解库结构：每条一行摘要（无原文），一次读完。')
out.append('> 更新：%s ｜ 主库 %d 条 + 通用区 %d 条 + 教程区 %d 篇 ｜ 主库全库指纹 `%s`' % (
    meta.get('updatedAt', '?'), len(data), len(gen), len(tut),
    (meta.get('完整性指纹') or {}).get('全库指纹', '?')))
out.append('> 取用原文的四种方式：')
out.append('> 1. 本仓库 `AI-全库.jsonl`（每行一条，含 original/zh 全文，可 grep）')
out.append('> 2. 本仓库 `视频提示词库-多模型.html` 的 data/general/tutorials 三个 script JSON 块')
out.append('> 3. 网页（GitHub Pages）工具栏「导出」→ AI 知识库包（浏览器内生成）')
out.append('> 4. 让维护者按 id 定点导出')
out.append('')
out.append('## 主库分类体系（%d 条）' % len(data))
out.append('')
cat_count = Counter(x['cat'] for x in data)
for c, n in cat_count.most_common():
    subs = Counter(x['sub'] for x in data if x['cat'] == c)
    sub_str = '、'.join('%s(%d)' % (s, k) for s, k in subs.most_common())
    out.append('- **%s**（%d 条）：%s' % (c, n, sub_str))
out.append('')
out.append('## 主库条目索引')
out.append('')
for x in data:
    out.append('- `%s`｜%s｜%s/%s｜%d字｜%s' % (
        x.get('id', '?'), x.get('name', '?'), x.get('cat', '?'), x.get('sub', '?'), len(x.get('original', '')),
        '、'.join(x.get('tags', [])[:3])))
out.append('')
out.append('## 通用区分类（%d 条）' % len(gen))
out.append('')
for c, n in Counter(x['cat'] for x in gen).most_common():
    out.append('- **%s**（%d 条）' % (c, n))
out.append('')
for x in gen:
    out.append('- `%s`｜%s｜%s/%s｜%s' % (
        x.get('id', '?'), x.get('name', '?'), x.get('cat', '?'), x.get('sub', '?'), (x.get('desc') or '')[:60]))
out.append('')
out.append('## 教程区（%d 篇）' % len(tut))
out.append('')
for x in tut:
    out.append('- `%s`｜%s｜%s' % (
        x['id'], x.get('title') or x.get('name', ''), (x.get('src') or '')[:60]))

open('AI导读索引.md', 'w', encoding='utf-8').write('\n'.join(out))
print('✓ AI导读索引.md：%.0fK 字符' % (os.path.getsize('AI导读索引.md') / 1000))

# ---------- AI-全库.jsonl ----------
with open('AI-全库.jsonl', 'w', encoding='utf-8') as f:
    for x in data:
        f.write(json.dumps({'区': '主库', **{k: x.get(k) for k in (
            'id', 'model', 'cat', 'sub', 'name', 'desc', 'tags', 'lang', 'original', 'zh', 'src')}},
            ensure_ascii=False) + '\n')
    for x in gen:
        f.write(json.dumps({'区': '通用区', **{k: x.get(k) for k in (
            'id', 'cat', 'sub', 'name', 'desc', 'original')}},
            ensure_ascii=False) + '\n')
    for x in tut:
        f.write(json.dumps({'区': '教程区', 'id': x['id'],
                            'title': x.get('title') or x.get('name'),
                            'src': x.get('src'), 'steps': x.get('steps')},
                           ensure_ascii=False) + '\n')
print('✓ AI-全库.jsonl：%.1fM 字节，%d 行' % (
    os.path.getsize('AI-全库.jsonl') / 1e6, len(data) + len(gen) + len(tut)))
