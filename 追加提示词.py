#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 追加提示词.py —— 简单追加模式（不 bump 版本号，原地写回，先备份后改）
# 用法：python 追加提示词.py <库.html> <新提示词.json>
# 设计：与"网站/信源收集"类项目一致——只往 HTML 里追加，文件名/版本标签保持不变；
#       每次执行先复制当前库进 视频提示词库_备份/ 时间戳副本，再写回同一文件，最后自检。
#       校验规则与"库维护工具.py 的 check"对齐：指纹不可变、无重复原文、字段齐全、
#       标题/简介中文、外文须有译文、标签 3-6 且合法。
import sys, os, re, json, hashlib, datetime, shutil

from 库共享定义 import (DATA_RE, META_RE, MODEL_TREE, TECH_OK, REQUIRED,
                       cjk, ok_tag, sha, check_fields, check_library,
                       DANGER_RE, NOISE_RE, ERR_TYPES)

PREFIX = {m: pf for f in MODEL_TREE for m, pf in f['versions'].items()}


def fam_of(m):
    m = str(m or '')
    for f in MODEL_TREE:
        if m == f['family'] or m.startswith(f['family']):
            return f['family']
    return re.split(r'[\s\-_]+', m)[0] or '其他'


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



def _refresh_ai_exports(html):
    """入库成功后自动刷新 AI 静态导出（AI导读索引.md / AI-全库.jsonl）。
    刷新失败视为入库失败——防止 AI 导出静默过期。"""
    import subprocess, sys as _s, os
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), '生成AI导出.py')
    if not os.path.exists(script):
        return  # 独立部署环境无此脚本时跳过
    r = subprocess.run([_s.executable, script, html], capture_output=True, text=True)
    if r.returncode != 0:
        print('× AI 静态导出刷新失败：')
        print(r.stdout[-500:] if r.stdout else '', r.stderr[-500:] if r.stderr else '')
        raise SystemExit(1)
    print(r.stdout.strip().split('\n')[-1] if r.stdout.strip() else '✓ AI 导出已刷新')


def save(h, data, meta, out):
    # 防 script 标签提前闭合：json.dumps 不转义 /，必须手动转义 </ 为 <\/
    def dump(x):
        return json.dumps(x, ensure_ascii=False, indent=1).replace('</', '<\\/')
    if meta:
        h = META_RE.sub(lambda m: m.group(1) + '\n' + dump(meta) + '\n' + m.group(3), h, count=1)
    h = DATA_RE.sub(lambda m: m.group(1) + '\n' + dump(data) + '\n' + m.group(3), h, count=1)
    # 写前断言：数据块内不得残留未转义危险串
    import re as _re
    for m in _re.finditer(r'<script id="(data|meta)"[^>]*>(.*?)</script>', h, _re.S):
        assert not _re.search(r'</script|<script(?![a-zA-Z])|<!--', m.group(2), _re.I), \
            '× %s 块内残留未转义危险串' % m.group(1)
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
    """委托共享模块 check_library：入库前与 verify 同一套标准
    （字段/指纹/完全重复/n-gram/注入/围栏/噪音/勘误登记）"""
    from 库共享定义 import check_library
    bad, warn = check_library(rows, meta)
    if warn:
        print('ℹ %d 条结构相似提示（不拦截）：' % len(warn))
        for w in warn[:10]:
            print('   ', w[0], w[1])
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
    _refresh_ai_exports(html)
    print('✓ 追加 %d 条 → 共 %d 条；版本标签未变（%s）；已生成备份 %s__%s'
          % (len(added), len(d2), m2.get('version'), ts, os.path.basename(html)))
    for e in added:
        print('   +', e['id'], e['model'], e['cat'], '/', e['sub'], e['name'])


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit('用法：python 追加提示词.py <库.html> <新提示词.json>')
    main(sys.argv[1], sys.argv[2])
