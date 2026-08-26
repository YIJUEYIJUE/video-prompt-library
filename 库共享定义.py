#!/usr/bin/env python3
"""共享校验模块（P2-3 消重复：审查 #27）

唯一权威来源：MODEL_TREE / TECH_OK / REQUIRED / 正则 / 校验函数。
库维护工具.py 与 追加提示词.py 一律 from 库共享定义 import *，
改注册表只改这一处，verify 与入库用同一套标准。
"""
import re, json, hashlib, sys

DATA_RE = re.compile(r'(<script[^>]*id="data"[^>]*>)(.*?)(</script>)', re.S)
META_RE = re.compile(r'(<script[^>]*id="meta"[^>]*>)(.*?)(</script>)', re.S)

MODEL_TREE = [
    {'family': 'Seedance', 'versions': {'Seedance 2.0': 'sd2', 'Seedance 2.5': 'sd25'}},
    {'family': '海螺', 'versions': {'海螺 H3': 'hl3'}},
    {'family': '可灵', 'versions': {'可灵 O3': 'klo3', '可灵 3.0': 'kl3'}},
]
MODELS = {m for f in MODEL_TREE for m in f['versions']}
TECH_OK = {'FPV', 'IMAX', 'CG', 'UE5', 'AI', 'VFX', 'HDR', 'LUT', 'Glitch',
           'Motion', 'Logo', 'Arri', 'Bokeh', 'Loop'}
REQUIRED = ['model', 'cat', 'sub', 'name', 'desc', 'tags', 'lang', 'original', 'src']

# 勘误登记合法类型（P2-1）
ERR_TYPES = {'OCR修正', '噪音清理', '重构拆分', '补全', '字段修正', '语义去重'}

# 危险串（P1-1 注入防护）
DANGER_RE = re.compile(r'</script|<script(?![a-zA-Z])|<!--', re.I)
# 噪音卡模式（P1-2 固化：commit 80ea097 事故）
NOISE_RE = re.compile(r'作者[：:]\s*\S|分享[到至].{0,6}平台|订阅.{0,8}频道|Try it in|Follow us|©\s*\d{4}')


def cjk(s):
    return bool(re.search(r'[\u4e00-\u9fff]', s or ''))


def ok_tag(x):
    x = str(x)
    if cjk(x):
        return True
    if x in TECH_OK:
        return True
    # 技术词：大写字母开头混合（FPV-Style / IMAX3D / iPhone16）
    if re.fullmatch(r'[A-Z][A-Za-z0-9-]{1,15}', x):
        return True
    # 数字开头的紧凑技术词：3D / 2D / 2.5D / 3A / 145BPM / 35mm / 60fps / 4K（收窄原 ^[0-9] 裸数字漏洞：数字后必须紧跟字母/单位）
    if re.fullmatch(r'[0-9][0-9.]{0,3}(D|A|BPM|mm|fps|K|k|s|Hz|P)', x):
        return True
    return False


def sha(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:16]


def check_fields(d, i, bad):
    """单条 9 字段校验（入库与全库共用）"""
    for f in REQUIRED:
        if f not in d or not d[f]:
            bad.append((i, '缺字段 %s' % f))
    if d.get('model') not in MODEL_TREE:
        bad.append((i, 'model 未登记（合法：%s）' % '/'.join(MODEL_TREE)))
    if d.get('cat') and not cjk(d['cat']):
        bad.append((i, 'cat 必须含汉字'))
    if d.get('name') and not cjk(d['name']):
        bad.append((i, '标题必须含汉字'))
    if d.get('desc') and not cjk(d['desc']):
        bad.append((i, '简介必须含汉字'))
    tg = d.get('tags') or []
    if not (3 <= len(tg) <= 6):
        bad.append((i, '标签数 %d 越界（3-6）' % len(tg)))
    for x in tg:
        if not ok_tag(x):
            bad.append((i, '标签不合规 %r（技术白名单/汉字/编号）' % x))
    o = d.get('original') or ''
    if d.get('chars') is not None and d['chars'] != len(o):
        bad.append((i, 'chars %d ≠ 实际 %d' % (d['chars'], len(o))))
    if '\ufffd' in o:
        bad.append((i, '原文含乱码字符'))
    # 注入防护（P1-1）
    if DANGER_RE.search(o):
        bad.append((i, '!! 原文含危险串 </script|<script|<!--（须转义或剔除）'))
    for f in ('original', 'zh'):
        v = d.get(f) or ''
        if isinstance(v, str) and DANGER_RE.search(v):
            bad.append((i, '!! %s 字段含危险串（须转义或剔除）' % f))
    # 围栏泄漏（P1-2）
    if isinstance(o, str) and '```' in o:
        bad.append((i, '原文含 %d 处 ``` 围栏泄漏' % o.count('```')))
    # 噪音卡（P1-2）
    if isinstance(o, str) and NOISE_RE.search(o):
        bad.append((i, '原文疑似含页脚/CTA 噪音：%s' % NOISE_RE.search(o).group(0)[:20]))
    return bad


def check_errata(meta, bad):
    """勘误登记格式校验（P2-1）"""
    for e in (meta.get('勘误登记') or []):
        for f in ('日期', '条目', '类型', '详情'):
            if not e.get(f):
                bad.append(('(meta)', '勘误登记缺字段 %s：%s' % (f, str(e)[:50])))
        if e.get('类型') and e['类型'] not in ERR_TYPES:
            bad.append(('(meta)', '勘误登记类型非法 %r（合法：%s）' % (e['类型'], '/'.join(sorted(ERR_TYPES)))))
    return bad
