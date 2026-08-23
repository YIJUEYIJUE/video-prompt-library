# -*- coding: utf-8 -*-
"""扩展区工具.py — 通用区(general)与教程区(tutorials)数据块的注入 / 追加 / 校验

用法：
  python 扩展区工具.py init   HTML文件  general.json  tutorials.json   # 首次注入两块
  python 扩展区工具.py append HTML文件  general|tutorials  批次.json   # 向某块追加
  python 扩展区工具.py verify HTML文件                                  # 校验两块指纹

设计：
  - general / tutorials 是独立 JSON 块（script id=general / tutorials），与 data 块平行；
  - meta['扩展区'] 登记两块的条目数与全块 SHA-256 指纹，篡改即被发现；
  - data 块逐字节不可动（断言保护）；meta 只增不改既有键。
"""
import json, re, sys, hashlib

BIRTH = '2026-08-24'


def sha(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:16]


def load(html_path):
    h = open(html_path, encoding='utf-8').read()
    meta = json.loads(re.search(r'<script id="meta"[^>]*>(.*?)</script>', h, re.S).group(1))
    return h, meta


def get_block(h, bid):
    m = re.search(r'<script id="%s"[^>]*>\n?(.*?)\n?</script>' % bid, h, re.S)
    return json.loads(m.group(1)) if m else None


def set_block(h, bid, obj):
    body = json.dumps(obj, ensure_ascii=False, indent=1)
    tag = '<script id="%s" type="application/json">\n%s\n</script>' % (bid, body)
    if re.search(r'<script id="%s"[^>]*>.*?</script>' % bid, h, re.S):
        return re.sub(r'<script id="%s"[^>]*>.*?</script>' % bid, lambda m: tag, h, count=1, flags=re.S)
    # 首次：插在 data 块结束标签之后
    m = re.search(r'(<script[^>]*id="data"[^>]*>.*?</script>)\n', h, re.S)
    assert m, 'data 块定位失败'
    return h[:m.end()] + tag + '\n' + h[m.end():]


def guard(h_before, h_after):
    d1 = re.search(r'<script[^>]*id="data"[^>]*>(.*?)</script>', h_before, re.S).group(1)
    d2 = re.search(r'<script[^>]*id="data"[^>]*>(.*?)</script>', h_after, re.S).group(1)
    assert d1 == d2, 'data 块被意外改动！'


def do_init(html_path, gen_path, tut_path):
    h, meta = load(html_path)
    gen = json.load(open(gen_path, encoding='utf-8'))
    tut = json.load(open(tut_path, encoding='utf-8'))
    h = set_block(h, 'general', gen)
    h = set_block(h, 'tutorials', tut)
    meta['扩展区'] = {
        '说明': '通用区(general)与教程区(tutorials)独立数据块；指纹算法与 data 块一致',
        'general': {'条目数': len(gen), '全块指纹': sha(json.dumps(gen, ensure_ascii=False))},
        'tutorials': {'条目数': len(tut), '全块指纹': sha(json.dumps(tut, ensure_ascii=False))},
    }
    meta['变更日志'].append({
        '日期': BIRTH, '内容': '新增顶层「通用区」（运镜词典 46 条，Higgsfield Camera Prompt Bank）'
        '与「教程区」（Higgsfield 耳机案例 3 步工作流 27 步）；网页增加区域切换导航'})
    meta['updatedAt'] = BIRTH
    h = re.sub(r'(<script id="meta"[^>]*>\n).*?(\n</script>)',
               lambda m: m.group(1) + json.dumps(meta, ensure_ascii=False, indent=1) + m.group(2), h, count=1, flags=re.S)
    guard(load(html_path)[0], h)
    open(html_path, 'w', encoding='utf-8').write(h)
    print('✓ 注入 general %d 条 / tutorials %d 篇；meta.扩展区 已登记指纹；data 块未动' % (len(gen), len(tut)))


def do_append(html_path, zone, batch_path):
    h, meta = load(html_path)
    assert zone in ('general', 'tutorials')
    blk = get_block(h, zone)
    assert blk is not None, '%s 块不存在，先 init' % zone
    batch = json.load(open(batch_path, encoding='utf-8'))
    ids = {e['id'] for e in blk}
    for e in batch:
        assert e['id'] not in ids, 'ID 重复：%s' % e['id']
        blk.append(e)
    h = set_block(h, zone, blk)
    meta['扩展区'][zone] = {'条目数': len(blk), '全块指纹': sha(json.dumps(blk, ensure_ascii=False))}
    meta['变更日志'].append({'日期': BIRTH, '内容': '%s区追加 %d 条（→ 共 %d）' % (zone, len(batch), len(blk))})
    meta['updatedAt'] = BIRTH
    h = re.sub(r'(<script id="meta"[^>]*>\n).*?(\n</script>)',
               lambda m: m.group(1) + json.dumps(meta, ensure_ascii=False, indent=1) + m.group(2), h, count=1, flags=re.S)
    guard(load(html_path)[0], h)
    open(html_path, 'w', encoding='utf-8').write(h)
    print('✓ %s 追加 %d 条 → 共 %d 条；指纹已更新' % (zone, len(batch), len(blk)))


def do_verify(html_path):
    h, meta = load(html_path)
    ok = True
    for zone in ('general', 'tutorials'):
        blk = get_block(h, zone)
        reg = meta.get('扩展区', {}).get(zone)
        if blk is None or reg is None:
            print('⚠ %s 块或登记缺失' % zone); ok = False; continue
        fp = sha(json.dumps(blk, ensure_ascii=False))
        n = len(blk)
        match = (fp == reg['全块指纹'] and n == reg['条目数'])
        print('%s %s：%d 条，指纹 %s %s' % ('✓' if match else '✗', zone, n, fp,
              '' if match else '≠ 登记 %s/%s' % (reg['条目数'], reg['全块指纹'])))
        ok = ok and match
    print('扩展区校验：%s' % ('全绿' if ok else '发现不一致'))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'init':
        do_init(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == 'append':
        do_append(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == 'verify':
        do_verify(sys.argv[2])
    else:
        print(__doc__)
