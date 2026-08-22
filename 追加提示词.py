#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 追加提示词.py —— 简单追加模式（不 bump 版本号，原地写回，先备份后改）
# 用法：python 追加提示词.py <库.html> <新提示词.json>
# 设计：与"网站/信源收集"类项目一致——只往 HTML 里追加，文件名/版本标签保持不变；
#       每次执行先复制当前库进 视频提示词库_备份/ 时间戳副本，再写回同一文件，最后自检。
#       校验规则与"库维护工具.py 的 check"对齐：指纹不可变、无重复原文、字段齐全、
#       标题/简介中文、外文须有译文、标签 3-6 且合法。
import sys, os, re, json, hashlib, datetime, shutil

DATA_RE = re.compile(r'(<script[^>]*id="data"[^>]*>)(.*?)(</script>)', re.S)
META_RE = re.compile(r'(<script id="meta" type="application/json">)(.*?)(</script>)', re.S)
MODEL_TREE = [
    {'family': 'Seedance', 'versions': {'Seedance 2.0': 'sd2', 'Seedance 2.5': 'sd25'}},
    {'family': '海螺', 'versions': {'海螺 H3': 'hl3'}},
    {'family': '可灵', 'versions': {'可灵 O3': 'klo3', '可灵 3.0': 'kl3'}},
]
PREFIX = {m: pf for f in MODEL_TREE for m, pf in f['versions'].items()}
TECH_OK = {'FPV', 'IMAX', 'CG', 'UE5', 'AI', 'VFX', 'HDR', 'LUT', 'Glitch',
           'Motion', 'Logo', 'Arri', 'Bokeh', 'Loop'}
REQUIRED = ['model', 'cat', 'sub', 'name', 'desc', 'tags', 'lang', 'original', 'src']


def fam_of(m):
    m = str(m or '')
    for f in MODEL_TREE:
        if m == f['family'] or m.startswith(f['family']):
            return f['family']
    return re.split(r'[\s\-_]+', m)[0] or '其他'


def cjk(s):
    return any('\u4e00' <= c <= '\u9fff' for c in str(s))


def ok_tag(x):
    x = str(x)
    if any('\u4e00' <= c <= '\u9fff' for c in x):
        return True
    if x in TECH_OK or re.match(r'^[0-9]', x) or x.isupper():
        return True
    return False


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


def next_id(rows, model):
    p = PREFIX.get(model) or (re.sub(r'[^a-z0-9]', '', str(model).lower())[:4] or 'x')
    n = 0
    for d in rows:
        m = re.match('^' + re.escape(p) + r'-(\d+)$', str(d.get('id', '')))
        if m:
            n = max(n, int(m.group(1)))
    return p, n


def check(rows, meta):
    """与库维护工具.py 的 check 对齐：返回问题列表 [(id, 原因)]"""
    bad = []
    fp = (meta.get('完整性指纹') or {}).get('逐条指纹') or {}
    seen = set()
    for d in rows:
        i = d['id']
        if i in seen:
            bad.append((i, 'id 重复'))
        seen.add(i)
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
    # 重复原文（去空白后逐字比对）
    norm = {}
    for d in rows:
        norm.setdefault(re.sub(r'\s+', '', d.get('original', '')), []).append(d['id'])
    for k, v in norm.items():
        if len(v) > 1:
            bad.append((v[0], '原文与 ' + '/'.join(str(x) for x in v[1:]) + ' 完全重复'))
    return bad


def main(html, newjson):
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
            sys.exit('× model 须写成「系列 + 空格 + 版本」，如 Seedance 2.5 / 海螺 H3 / 可灵 O3，当前：%s' % it['model'])
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
    # 全量校验（对齐库维护工具.py 的 check）
    bad = check(rows, meta)
    if bad:
        print('× 校验未通过，未写出任何文件：')
        for b in bad[:30]:
            print('   ', b[0], b[1])
        sys.exit(1)
    # —— 先备份，再原地写回（版本标签 version 保持不变）——
    bakdir = os.path.join(os.path.dirname(os.path.abspath(html)), '视频提示词库_备份')
    os.makedirs(bakdir, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    shutil.copy2(html, os.path.join(bakdir, ts + '__' + os.path.basename(html)))
    per = {d['id']: sha(d['original']) for d in rows}
    today = datetime.date.today().isoformat()
    meta['updatedAt'] = today
    meta['完整性指纹'] = {
        '条目数': len(rows),
        '原文总字数': sum(len(d['original']) for d in rows),
        # 全库指纹 = 按 id 排序拼接逐条指纹后 sha256 前 16 位（与说明 §3 一致）
        '全库指纹': hashlib.sha256(''.join(per[k] for k in sorted(per)).encode()).hexdigest()[:16],
        '逐条指纹': per}
    meta.setdefault('变更日志', []).append({
        '日期': today,
        '内容': '追加 %d 条（%s），版本标签保持 %s' % (len(added), '、'.join(sorted(set(x['model'] for x in added))), meta.get('version'))})
    save(h, rows, meta, html)
    # 写回后自检：条数对、老条目原文未动、版本标签未变
    _, d2, m2 = load(html)
    assert len(d2) == len(rows), '条目数对不上'
    assert all(x['original'] == before[x['id']] for x in d2 if x['id'] in before), '!! 老条目原文被改动'
    print('✓ 追加 %d 条 → 共 %d 条；版本标签未变（%s）；已生成备份 %s__%s'
          % (len(added), len(d2), m2.get('version'), ts, os.path.basename(html)))
    for e in added:
        print('   +', e['id'], e['model'], e['cat'], '/', e['sub'], e['name'])


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit('用法：python 追加提示词.py <库.html> <新提示词.json>')
    main(sys.argv[1], sys.argv[2])
