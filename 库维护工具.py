#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 提示词库维护工具 v2（模型两级：系列 → 版本）
# 用法：
#   python3 库维护工具.py verify <库.html>
#   python3 库维护工具.py add    <库.html> <新提示词.json> [输出.html]
#   python3 库维护工具.py export <库.html> [输出目录]
# 铁律：绝不原地覆盖；老条目 original 指纹必须全部不变，任一不符立即中止。
import sys, os, re, json, hashlib, datetime

DATA_RE = re.compile(r'(<script[^>]*id="data"[^>]*>)(.*?)(</script>)', re.S)
META_RE = re.compile(r'(<script id="meta" type="application/json">)(.*?)(</script>)', re.S)
# 模型两级注册表：顶层系列 → 具体版本 → id 前缀
MODEL_TREE = [
    {'family': 'Seedance', 'versions': {'Seedance 2.0': 'sd2', 'Seedance 2.5': 'sd25'}},
    {'family': '海螺', 'versions': {'海螺 H3': 'hl3'}},
    {'family': '可灵', 'versions': {'可灵 O3': 'klo3', '可灵 3.0': 'kl3'}},
]
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
TECH_OK = {'FPV', 'IMAX', 'CG', 'UE5', 'AI', 'VFX', 'HDR', 'LUT', 'Glitch', 'Motion', 'Logo', 'Arri', 'Bokeh', 'Loop'}
def ok_tag(x):
    x = str(x)
    if any('\u4e00' <= c <= '\u9fff' for c in x):
        return True
    if x in TECH_OK or re.match(r'^[0-9]', x) or x.isupper():
        return True
    return False
REQUIRED = ['model', 'cat', 'sub', 'name', 'desc', 'tags', 'lang', 'original', 'src']

def cjk(s):
    return any('\u4e00' <= c <= '\u9fff' for c in str(s))

def sha(s):
    return hashlib.sha256(str(s).encode()).hexdigest()[:16]

def load(path):
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
    return h, data, (meta or {})

def save(h, data, meta, out):
    if meta:
        h = META_RE.sub(lambda m: m.group(1) + '\n' + json.dumps(meta, ensure_ascii=False, indent=1) + '\n' + m.group(3), h, count=1)
    h = DATA_RE.sub(lambda m: m.group(1) + '\n' + json.dumps(data, ensure_ascii=False, indent=1) + '\n' + m.group(3), h, count=1)
    open(out, 'w', encoding='utf-8').write(h)

def check(data, meta):
    bad = []
    fp = (meta.get('完整性指纹') or {}).get('逐条指纹') or {}
    seen_id = set()
    for d in data:
        i = d.get('id', '?')
        if i in seen_id:
            bad.append((i, 'id 重复'))
        seen_id.add(i)
        for f in REQUIRED:
            if not d.get(f):
                bad.append((i, '缺字段 ' + f))
        o = d.get('original') or ''
        if '\ufffd' in o:
            bad.append((i, '原文含乱码字符'))
        if d.get('chars') != len(o):
            bad.append((i, 'chars 与原文长度不符'))
        if i in fp and fp[i] != sha(o):
            bad.append((i, '!! 原文指纹不符（原文被改动）'))
        if not cjk(d.get('name', '')):
            bad.append((i, '标题不是中文'))
        if not cjk(d.get('desc', '')):
            bad.append((i, '简介不是中文'))
        if d.get('lang') != 'zh' and not str(d.get('zh') or '').strip():
            bad.append((i, '外文条目缺中文译文 zh'))
        t = d.get('tags') or []
        if not (3 <= len(t) <= 6):
            bad.append((i, '标签数 %d 不在 3-6' % len(t)))
        for x in t:
            if not ok_tag(x):
                bad.append((i, '非中文标签：' + str(x)))
    dup = {}
    for d in data:
        dup.setdefault(sha(re.sub(r'\s+', '', d.get('original', ''))), []).append(d.get('id'))
    for v in dup.values():
        if len(v) > 1:
            bad.append((v[0], '原文与 ' + '/'.join(str(x) for x in v[1:]) + ' 完全重复'))
    return bad

def cmd_verify(html):
    h, data, meta = load(html)
    bad = check(data, meta)
    fp = (meta.get('完整性指纹') or {}).get('逐条指纹') or {}
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
    if bad:
        print('× 发现 %d 个问题：' % len(bad))
        for b in bad[:30]:
            print('   ', b[0], b[1])
    else:
        print('✓ 全部通过：原文指纹一致、字段齐全、标题简介中文、标签合规、无重复')
    return 1 if bad else 0

def next_id(rows, model):
    p = PREFIX.get(model) or (re.sub(r'[^a-z0-9]', '', str(model).lower())[:4] or 'x')
    n = 0
    for d in rows:
        m = re.match('^' + re.escape(p) + r'-(\d+)$', str(d.get('id', '')))
        if m:
            n = max(n, int(m.group(1)))
    return p, n

def cmd_add(html, newjson, out=None):
    h, data, meta = load(html)
    before = {d['id']: d['original'] for d in data}
    items = json.load(open(newjson, encoding='utf-8'))
    if isinstance(items, dict):
        items = [items]
    added = []
    for it in items:
        for f in REQUIRED:
            if not it.get(f):
                sys.exit('× 新条目缺字段 %s：%s' % (f, it.get('name', '(无标题)')))
        if not re.search(r'\s', str(it['model']).strip()):
            sys.exit('× model 必须写成「系列 + 空格 + 版本」，如 Seedance 2.5 / 海螺 H3 / 可灵 O3，当前：%s' % it['model'])
        p, n = next_id(data + added, it['model'])
        lang = it.get('lang', 'zh')
        added.append({
            'id': '%s-%03d' % (p, n + 1), 'model': it['model'], 'cat': it['cat'], 'sub': it['sub'],
            'name': it['name'], 'desc': it['desc'], 'tags': it['tags'], 'lang': lang,
            'langname': it.get('langname', '中文' if lang == 'zh' else str(lang).upper()),
            'zh': it.get('zh', ''), 'original': it['original'], 'chars': len(it['original']),
            'src': it['src'], 'srcs': it.get('srcs') or [it['src']], 'num': it.get('num', ''),
            'primary': it.get('primary', True), 'sha1': sha(it['original'])})
    rows = data + added
    bad = check(rows, meta)
    if bad:
        print('× 校验未通过，未写出任何文件：')
        for b in bad[:30]:
            print('   ', b[0], b[1])
        sys.exit(1)
    per = {d['id']: sha(d['original']) for d in rows}
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    old = str(meta.get('version', 'v0'))
    nv = 'v%d' % (int(re.sub(r'\D', '', old) or 0) + 1)
    meta['version'] = nv
    meta['updatedAt'] = today
    meta['完整性指纹'] = {'条目数': len(rows), '原文总字数': sum(len(d['original']) for d in rows),
                        '全库指纹': hashlib.sha256(''.join(per[k] for k in sorted(per)).encode()).hexdigest(),
                        '逐条指纹': per}
    meta.setdefault('变更日志', []).append(
        {'日期': today, '版本': nv,
         '内容': '追加 %d 条（%s），老条目原文指纹全部未变' % (len(added), '、'.join(sorted(set(x['model'] for x in added))))})
    if not out:
        out = re.sub(r'(-v\d+)?\.html$', '', html) + '-' + nv + '.html'
    if os.path.abspath(out) == os.path.abspath(html):
        sys.exit('× 拒绝原地覆盖，请换一个输出文件名')
    save(h, rows, meta, out)
    _, d2, m2 = load(out)
    assert len(d2) == len(rows), '条目数对不上'
    assert all(x['original'] == before[x['id']] for x in d2 if x['id'] in before), '!! 老条目原文被改动'
    print('✓ 追加 %d 条 → 共 %d 条；老条目原文指纹全部未变' % (len(added), len(d2)))
    print('✓ 新文件：%s（原文件未动）' % out)
    for e in added:
        print('   +', e['id'], e['model'], e['cat'], '/', e['sub'], e['name'])
    return 0

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
    if not a or a[0] not in ('verify', 'add', 'export'):
        print(__doc__ or '')
        print('用法：verify <库.html> ｜ add <库.html> <新提示词.json> [输出.html] ｜ export <库.html> [目录]')
        sys.exit(2)
    if a[0] == 'verify':
        sys.exit(cmd_verify(a[1]))
    if a[0] == 'add':
        sys.exit(cmd_add(a[1], a[2], a[3] if len(a) > 3 else None))
    sys.exit(cmd_export(a[1], a[2] if len(a) > 2 else None))