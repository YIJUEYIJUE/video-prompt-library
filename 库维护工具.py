#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 提示词库维护工具 v2（模型两级：系列 → 版本）
# 用法：
#   python3 库维护工具.py verify <库.html>
#   （add 已废弃删除：与 追加提示词.py 功能重复且指纹算法 64 位不一致，2026-08-26 对抗式审查 P1-26）
#   python3 库维护工具.py backup <库.html> [保留份数=10]（清理旧备份，防 100MB 膨胀）
#   python3 库维护工具.py export <库.html> [输出目录]
# 铁律：绝不原地覆盖；老条目 original 指纹必须全部不变，任一不符立即中止。
import sys, os, re, json, hashlib, datetime

from 库共享定义 import (DATA_RE, META_RE, MODEL_TREE, MODELS, TECH_OK, REQUIRED,
                       ERR_TYPES, DANGER_RE, NOISE_RE,
                       cjk, ok_tag, sha, check_fields, check_errata)
# 模型两级注册表：顶层系列 → 具体版本 → id 前缀
MODEL_TREE = __import__('库共享定义').MODEL_TREE
PREFIX = {m: pf for f in MODEL_TREE for m, pf in f['versions'].items()}
def fam_of(m):
    m = str(m or '')
    for f in MODEL_TREE:
        if m == f['family'] or m.startswith(f['family']):
            return f['family']
    return re.split(r'[\s\-_]+', m)[0] or '其他'
def ver_of(m):
    f = fam_of(m)
    return str(m or '')[len(f):].strip() or '默认'



def load(path, strict=True):
    h = open(path, encoding='utf-8').read()
    def pick(rx, opener):
        for m in rx.finditer(h):
            body = m.group(2)
            if body.lstrip()[:1] == opener:
                try:
                    return m, json.loads(body)
                except Exception:
                    continue
        return None, None
    dm, data = pick(DATA_RE, '[')
    if data is None:
        sys.exit('× 找不到可解析的数据块 script#data')
    mm, meta = pick(META_RE, '{')
    if meta is None:
        sys.exit('× 找不到可解析的 meta 块 script#meta（fail-closed：指纹基准缺失即拒判）')
    if strict and not ((meta.get('完整性指纹') or {}).get('逐条指纹')):
        sys.exit('× meta 缺少 完整性指纹.逐条指纹 登记（fail-closed：无基准即拒判，旧版会静默跳过全部校验）')
    return h, data, meta


_LAST_WARN = []  # check() 的警告通道（结构相似提示等，不拦截写入）

def check(data, meta):
    """委托共享模块 check_library（P2-3 消重复后唯一权威实现）"""
    from 库共享定义 import check_library
    bad, warn = check_library(data, meta)
    _LAST_WARN.clear()
    _LAST_WARN.extend(warn)
    return bad


def cmd_verify(html):
    h, data, meta = load(html)
    bad = check(data, meta)
    fp = (meta.get('完整性指纹') or {}).get('逐条指纹') or {}
    uncovered = [d.get('id', '?') for d in data if d.get('id') not in fp]
    if uncovered:
        print('⚠ %d 条未登记指纹（不在逐条指纹表内，保护缺口）：%s' % (len(uncovered), '、'.join(map(str, uncovered[:10]))))
        bad.append(('(全局)', '%d 条未登记指纹' % len(uncovered)))
    print('文件：%s' % html)
    print('版本：%s ｜ 条目：%d ｜ 原文总字数：%d'
          % (meta.get('version', '?'), len(data), sum(len(d.get('original', '')) for d in data)))
    tree = {}
    for d in data:
        tree.setdefault(fam_of(d.get('model')), {}).setdefault(d.get('model', '?'), 0)
        tree[fam_of(d.get('model'))][d.get('model', '?')] += 1
    for fam in sorted(tree):
        vs = tree[fam]
        print('  %s（%d）' % (fam, sum(vs.values())), '：', '、'.join('%s %d' % (ver_of(k), v) for k, v in sorted(vs.items())))
    unreg = sorted(set(d.get('model', '?') for d in data) - set(PREFIX))
    if unreg:
        print('  ⚠ 未登记到模型注册表：%s（仍可显示，建议补登记）' % '、'.join(unreg))
    print('指纹可比对条目：%d' % len(fp))
    warn = _LAST_WARN
    if warn:
        print('ℹ %d 条结构相似提示（同模板变体，不拦截）：' % len(warn))
        for w in warn[:10]:
            print('   ', w[0], w[1])
    if bad:
        print('× 发现 %d 个问题：' % len(bad))
        for b in bad[:30]:
            print('   ', b[0], b[1])
    else:
        print('✓ 全部通过：原文指纹一致、字段齐全、标题简介中文、标签合规、无重复；围栏/噪音/注入扫描清')
    return 1 if bad else 0

def next_id(rows, model):
    p = PREFIX.get(model) or (re.sub(r'[^a-z0-9]', '', str(model).lower())[:4] or 'x')
    n = 0
    for d in rows:
        m = re.match('^' + re.escape(p) + r'-(\d+)$', str(d.get('id', '')))
        if m:
            n = max(n, int(m.group(1)))
    return p, n


def _tally(data):
    fam, cat, tag, chars = {}, {}, {}, 0
    for d in data:
        f = fam_of(d.get('model'))
        fam.setdefault(f, {})
        fam[f][d['model']] = fam[f].get(d['model'], 0) + 1
        cat.setdefault(d['cat'], {})
        cat[d['cat']][d['sub']] = cat[d['cat']].get(d['sub'], 0) + 1
        for t in d.get('tags', []):
            tag[t] = tag.get(t, 0) + 1
        chars += len(d.get('original', ''))
    return fam, cat, tag, chars


def _md_val(v, ind=0):
    pad = '  ' * ind
    if v is None:
        return ''
    if isinstance(v, (str, int, float)):
        return pad + '- ' + str(v) + '\n'
    if isinstance(v, list):
        return ''.join(_md_val(x, ind) for x in v)
    out = []
    for k, x in v.items():
        if x is None:
            continue
        if isinstance(x, (str, int, float)):
            out.append(pad + '- **%s**：%s\n' % (k, x))
        else:
            out.append(pad + '- **%s**\n' % k + _md_val(x, ind + 1))
    return ''.join(out)


def ai_doc(data, meta, full=True):
    """full=True -> AI 知识库包（整库无损镜像）；full=False -> AI 导读索引（无原文）"""
    fam, cat, tag, chars = _tally(data)
    zh = sum(1 for d in data if d.get('lang') == 'zh')
    fp = meta.get('完整性指纹') or {}
    fields = meta.get('字段说明') or {}
    o = []
    o.append('# 视频提示词库 · %s\n' % ('AI 知识库包（整库无损镜像）' if full else 'AI 导读索引（轻量版）'))
    o.append('## 0. 这份文件是什么\n')
    if full:
        o.append('这是提示词库网页的**无损文本镜像**：除了样式与交互脚本，网页里的全部内容都在这里——入库规则、模型注册表、分类体系、字段定义，以及 %d 条条目的全部 %d 个字段（含逐字原文、中文译文、多源溯源、序号、指纹）。你可以只读这一份，不需要再去解析网页。\n' % (len(data), len(fields) + 1))
        o.append('- 想省 token：改用「AI 导读索引」（同样的第 0–7 节，条目只留一行）。')
        o.append('- 想入向量库：改用 JSONL。')
        o.append('- 要往库里写新条目：看第 3 节。\n')
    else:
        o.append('这是轻量索引：规则、体系、字段与「AI 知识库包」完全一致，但**条目只留一行摘要**，不含原文、译文与溯源。适合先读它建立全局认知，需要原文时再取「AI 知识库包」或 JSONL。\n')
    o.append('## 1. 基本信息\n')
    o.append('- 库名：%s' % meta.get('库名', '视频提示词库'))
    o.append('- 版本：%s（更新 %s）' % (meta.get('version', '?'), meta.get('updatedAt', '?')))
    o.append('- 条目：%d 条（中文原版 %d · 外文原版 %d，外文均附中文译文）' % (len(data), zh, len(data) - zh))
    o.append('- 原文总字数：%d' % chars)
    o.append('- 全库指纹：%s' % fp.get('全库指纹', '-'))
    o.append('- 维护记录：%s\n' % meta.get('维护记录', '见外置《维护日志.md》'))
    o.append('## 2. 怎么检索与引用\n')
    o.append('- 先定「模型系列 + 版本」，再定「大类/小类」，最后用标签或关键词缩范围。')
    o.append('- 引用提示词一律逐字照搬原文，不改写、不润色、不翻译；需要中文理解时看译文。')
    o.append('- 外文条目的标题与简介都是中文，但 prompt 本体保持原语种。\n')
    o.append('## 3. 入库规则（给要往库里写新条目的 AI）\n')
    o.append(_md_val(meta.get('给AI的接手说明') or {}))
    o.append('铁律：\n')
    o.append(_md_val(meta.get('录入规约') or []))
    o.append('## 4. 模型结构（两级：系列 → 版本）\n')
    o.append('【注册表】\n')
    o.append(_md_val(meta.get('模型注册表') or {}))
    o.append('【本文件实际分布】\n')
    for f in sorted(fam):
        vs = fam[f]
        o.append('- **%s**（%d 条）：%s' % (f, sum(vs.values()),
                 '、'.join('%s %d 条' % (ver_of(k), vs[k]) for k in sorted(vs))))
    o.append('\n## 5. 分类体系\n')
    o.append('| 大类 | 条数 | 小类（条数） |')
    o.append('|---|---|---|')
    for c in sorted(cat, key=lambda x: -sum(cat[x].values())):
        subs = cat[c]
        o.append('| %s | %d | %s |' % (c, sum(subs.values()),
                 '、'.join('%s（%d）' % (k, subs[k]) for k in sorted(subs, key=lambda x: -subs[x]))))
    tops = sorted(tag, key=lambda x: -tag[x])
    o.append('\n## 6. 标签表（共 %d 个）\n' % len(tops))
    o.append(' · '.join('%s %d' % (t, tag[t]) for t in tops))
    o.append('\n## 7. 字段说明（每条目 %d 个字段）\n' % len(fields))
    o.append(_md_val(fields))
    o.append('## 8. 条目（%d 条）\n' % len(data))
    if not full:
        o.append('| ID | 模型 | 大类 / 小类 | 标题 | 简介 | 标签 | 语种 | 字数 |')
        o.append('|---|---|---|---|---|---|---|---|')
        cl = lambda x: str(x if x is not None else '').replace('|', '｜').replace('\n', ' ')
        for d in data:
            o.append('| %s | %s | %s / %s | %s | %s | %s | %s | %s |' % (
                d['id'], cl(d.get('model')), cl(d['cat']), cl(d['sub']), cl(d['name']),
                cl(d['desc']), cl('、'.join(d.get('tags', []))),
                cl(d.get('langname') or d.get('lang')), d.get('chars', 0)))
        o.append('\n> 需要原文、译文、溯源与指纹：取「AI 知识库包」或 JSONL。')
        return '\n'.join(o) + '\n'
    by = {}
    for d in data:
        by.setdefault(d['cat'], {}).setdefault(d['sub'], []).append(d)
    for c in sorted(by, key=lambda x: -sum(len(v) for v in by[x].values())):
        o.append('\n### ' + c)
        for sb in sorted(by[c], key=lambda x: -len(by[c][x])):
            o.append('\n#### ' + sb)
            for d in by[c][sb]:
                o.append('\n##### %s\n' % d['name'])
                o.append('- ID：%s ｜ 模型：%s（系列 %s / 版本 %s）'
                         % (d['id'], d.get('model', ''), fam_of(d.get('model')), ver_of(d.get('model'))))
                o.append('- 分类：%s / %s' % (d['cat'], d['sub']))
                o.append('- 标签：%s' % '、'.join(d.get('tags', [])))
                o.append('- 语种：%s（%s） ｜ 字数：%s ｜ 序号：%s ｜ 指纹：%s'
                         % (d.get('langname', ''), d.get('lang', ''), d.get('chars', ''),
                            d.get('num', ''), d.get('sha1', '')))
                o.append('- 主源：%s ｜ 显示来源：%s' % (d.get('primary', ''), d.get('src', '')))
                o.append('- 全部溯源：%s' % (' ｜ '.join(d.get('srcs', [])) or '—'))
                o.append('- 简介：%s\n' % d['desc'])
                o.append('【提示词原文】\n')
                fence = '~~~~' if '```' in d['original'] else '```'
                o.append(fence + 'text\n' + d['original'] + '\n' + fence)
                if d.get('zh'):
                    o.append('\n【中文译文】\n')
                    o.append(d['zh'])
    o.append('\n## 9. 附录 A：逐条原文指纹\n')
    o.append('用于校验原文是否被改动（sha256 前 16 位）。\n')
    o.append('| ID | 指纹 |')
    o.append('|---|---|')
    per = fp.get('逐条指纹') or {}
    for d in data:
        if per.get(d['id']):
            o.append('| %s | %s |' % (d['id'], per[d['id']]))
    o.append('\n## 10. 附录 B：版本历史（摘要）\n')
    o.append(_md_val(meta.get('变更日志') or []))
    o.append('完整维护记录在外置《维护日志.md》。')
    return '\n'.join(o) + '\n'


def changelog_md(data, meta):
    fp = meta.get('完整性指纹') or {}
    o = ['# 提示词库 · 维护日志\n',
         '> 本文件由「库维护工具.py export」自动生成，网页内不再堆维护文本。每次改库后重新导出即可。\n',
         '## 当前状态\n',
         '- 版本：%s（更新 %s）' % (meta.get('version', '?'), meta.get('updatedAt', '?')),
         '- 条目数：%d' % len(data),
         '- 原文总字数：%s' % fp.get('原文总字数', sum(len(d.get('original', '')) for d in data)),
         '- 全库指纹：%s\n' % fp.get('全库指纹', '-'),
         '## 版本历史\n']
    for e in (meta.get('变更日志') or []):
        o.append('- %s' % (e if isinstance(e, str) else
                           '%s · %s · %s' % (e.get('版本', ''), e.get('日期', ''), e.get('内容', ''))))
    o.append('\n## 每次维护请手写一行\n')
    o.append('格式：`日期 · 做了什么 · 条数变化 · 校验结果`，例：\n')
    o.append('- 2026-08-21 · 新增可灵 O3 提示词 3 条 · 191 → 194 · verify 全绿\n')
    return '\n'.join(o)


def cmd_backup(html, keep=10):
    import glob, os
    d = os.path.join(os.path.dirname(os.path.abspath(html)) or '.', '视频提示词库_备份')
    if not os.path.isdir(d):
        print('备份目录不存在，无旧备份可清'); return 0
    files = sorted(glob.glob(os.path.join(d, '*.html')), key=os.path.getmtime, reverse=True)
    old = files[keep:]
    for f in old:
        os.remove(f)
        print('  删', os.path.basename(f))
    print('✓ 备份清理：保留 %d 份，删 %d 份（共 %.1fMB）' % (min(keep, len(files)), len(old),
          sum(os.path.getsize(f) for f in files[:keep]) / 1e6))
    return 0

def cmd_export(html, outdir=None):
    h, data, meta = load(html)
    outdir = outdir or os.path.dirname(os.path.abspath(html))
    n = len(data)
    base = os.path.join(outdir, '提示词库-全库-%d条' % n)
    slim = [{'id': d['id'], 'model': d['model'], 'model_family': fam_of(d.get('model')),
             'model_version': ver_of(d.get('model')), 'category': d['cat'], 'subcategory': d['sub'],
             'title': d['name'], 'summary': d['desc'], 'tags': d.get('tags', []), 'lang': d.get('lang'),
             'source': d.get('src'), 'chars': d.get('chars'), 'prompt': d['original'],
             'prompt_zh': d.get('zh', '')} for d in data]
    open(base + '.jsonl', 'w', encoding='utf-8').write('\n'.join(json.dumps(x, ensure_ascii=False) for x in slim))
    open(base + '.json', 'w', encoding='utf-8').write(json.dumps(
        {'schema': meta.get('字段说明'), 'version': meta.get('version'), 'rules': meta.get('录入规约'),
         'count': n, 'items': slim}, ensure_ascii=False, indent=1))
    by = {}
    for d in data:
        by.setdefault(d['cat'], {}).setdefault(d['sub'], []).append(d)
    md = ['# 视频提示词库导出\n', '- 条目：%d' % n, '- 版本：%s' % meta.get('version', '?'),
          '- 说明：代码块内为源文档逐字原文，可直接投喂视频模型；外文条目附中文译文。\n']
    for c in sorted(by):
        md.append('\n## ' + c)
        for s in sorted(by[c]):
            md.append('\n### ' + s)
            for d in by[c][s]:
                md.append('\n#### %s\n\n- ID：%s ｜ 模型：%s ｜ 来源：%s ｜ %s 字\n- 标签：%s\n- 简介：%s\n'
                          % (d['name'], d['id'], d['model'], d.get('src', ''), d.get('chars', ''),
                             '、'.join(d.get('tags', [])), d['desc']))
                md.append('```text\n' + d['original'] + '\n```')
                if d.get('zh'):
                    md.append('\n<details><summary>中文译文</summary>\n\n' + d['zh'] + '\n\n</details>')
    open(base + '.md', 'w', encoding='utf-8').write('\n'.join(md))
    open(base + '.txt', 'w', encoding='utf-8').write(
        '\n\n'.join('### ' + d['name'] + '\n' + d['original'] for d in data))
    p_pack = os.path.join(outdir, 'AI知识库包-全库-%d条.md' % n)
    p_idx = os.path.join(outdir, 'AI导读索引-全库-%d条.md' % n)
    p_log = os.path.join(outdir, '维护日志.md')
    open(p_pack, 'w', encoding='utf-8').write(ai_doc(data, meta, True))
    open(p_idx, 'w', encoding='utf-8').write(ai_doc(data, meta, False))
    open(p_log, 'w', encoding='utf-8').write(changelog_md(data, meta))
    kb = lambda p: os.path.getsize(p) // 1024
    print('✓ 已导出（%d 条）：' % n)
    print('  给 AI：%s（%d KB）' % (os.path.basename(p_pack), kb(p_pack)))
    print('  给 AI：%s（%d KB）' % (os.path.basename(p_idx), kb(p_idx)))
    print('  给 AI：%s.jsonl（%d KB）' % (os.path.basename(base), kb(base + '.jsonl')))
    print('  给人：%s.md / .json / .txt' % os.path.basename(base))
    print('  日志：%s' % os.path.basename(p_log))
    return 0

if __name__ == '__main__':
    a = sys.argv[1:]
    if not a or a[0] not in ('verify', 'backup', 'export'):
        print(__doc__ or '')
        print('用法：verify <库.html> ｜ backup <库.html> [保留份数=10] ｜ export <库.html> [目录]（add 已废弃删除）')
        sys.exit(2)
    if a[0] == 'verify':
        sys.exit(cmd_verify(a[1]))
    if a[0] == 'backup':
        sys.exit(cmd_backup(a[1] if len(a) > 1 else '视频提示词库-多模型.html', int(a[2]) if len(a) > 2 else 10))
    sys.exit(cmd_export(a[1], a[2] if len(a) > 2 else None))