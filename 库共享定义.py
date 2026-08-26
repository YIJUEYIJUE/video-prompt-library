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
    # 技术词：大写字母开头的混合串（FPV-Style / IMAX3D / TODO 亦放行——
    # 注意：纯大写词 TODO/ASDF 仍会过；mixed-case 如 FPV-Style 比旧版 isupper 更宽松，属有意放宽）
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
    if d.get('model') not in MODELS:
        bad.append((i, 'model 未登记（合法：%s）' % '/'.join(sorted(MODELS))))
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
    # 注入防护（P1-1）：original/zh 由下方循环统一报，避免双报
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


def check_library(data, meta):
    """全库内容校验（库维护工具.verify 与 追加提示词.入库前校验 共用同一套标准）
    返回 (bad, warn)：bad 非空即拒判/拒写；warn 仅提示。
    """
    bad, warn = [], []
    fp = (meta.get('完整性指纹') or {}).get('逐条指纹') or {}
    seen_id = set()
    for d in data:
        i = d.get('id', '?')
        if i in seen_id:
            bad.append((i, 'id 重复'))
        seen_id.add(i)
        check_fields(d, i, bad)
        o = d.get('original') or ''
        if i in fp and fp[i] != sha(o):
            bad.append((i, '!! 原文指纹不符（原文被改动）'))
    # 全库指纹一致性（三轮审查修复：P2-4 id 重命名后曾漂移而无人发现）
    fp_all = (meta.get('完整性指纹') or {}).get('全库指纹')
    if fp_all:
        recompute = hashlib.sha256(''.join(fp[k] for k in sorted(fp)).encode()).hexdigest()[:16]
        if recompute != fp_all:
            bad.append(('(meta)', '!! 全库指纹不符：登记 %s vs 重算 %s（逐条指纹被改后未重算全库）' % (fp_all, recompute)))
        if d.get('lang') != 'zh' and not str(d.get('zh') or '').strip():
            bad.append((i, '外文条目缺中文译文 zh'))
    # 完全重复（去空白逐字）
    norm = {}
    for d in data:
        norm.setdefault(re.sub(r'\s+', '', d.get('original', '')), []).append(d.get('id'))
    for v in norm.values():
        if len(v) > 1:
            bad.append((v[0], '原文与 ' + '/'.join(str(x) for x in v[1:]) + ' 完全重复'))
    # n-gram 近重复：>0.90 红警（复制粘贴/翻译副本级，实测真雷 99-100%）
    # 0.45-0.90 警告（模板变体/规格话术复用，实测 67-88% 合法）
    by_cat = {}
    for d in data:
        o = re.sub(r'\s+', '', d.get('original', ''))
        if len(o) >= 40:
            by_cat.setdefault(d.get('cat', '?'), []).append((d.get('id', '?'), set(o[j:j+2] for j in range(len(o)-1))))
    exempt = {(p['对'][0], p['对'][1]) for p in (meta.get('相似豁免') or [])}
    exempt |= {(b, a) for a, b in exempt}
    for cat, lst in by_cat.items():
        lst = lst[:400]
        for a in range(len(lst)):
            ida, ga = lst[a]
            for b in range(a + 1, len(lst)):
                idb, gb = lst[b]
                if (ida, idb) in exempt:
                    continue
                inter = len(ga & gb)
                if inter:
                    sim = inter / len(ga | gb)
                    if sim > 0.90:
                        bad.append((ida, '与 %s 语义高度重复（n-gram 相似度 %.0f%%，翻译副本/复制粘贴级）' % (idb, 100 * sim)))
                    elif sim > 0.45:
                        warn.append((ida, '与 %s 结构相似（n-gram %.0f%%，模板变体/规格话术复用）' % (idb, 100 * sim)))
    check_errata(meta, bad)
    return bad, warn
