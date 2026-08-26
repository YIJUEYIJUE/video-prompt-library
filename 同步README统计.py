# -*- coding: utf-8 -*-
"""同步README统计.py — 把 README 的规模行 / 分类实况表 / §12 变更记录同步到 HTML 库现状

用法（仓库根目录）：python 同步README统计.py 视频提示词库-多模型.html
设计原则：
  1. 幂等 —— README 已是现状时零改动（重复运行安全）；
  2. 软失败 —— 任何异常只打警告、退出码恒为 0，绝不阻断 CI 的入库提交（数据优先，README 可后补）；
  3. 只读 HTML 的 data/meta 块，绝不写 HTML（唯一数据源只能由 追加提示词.py 写入）。
"""
import json, re, sys
from collections import Counter, OrderedDict

HTML = sys.argv[1] if len(sys.argv) > 1 else '视频提示词库-多模型.html'
README = 'README.md'


def soft_fail(msg):
    print('⚠ 同步README统计：{}（不影响入库提交，README 待人工同步）'.format(msg))
    sys.exit(0)  # 软失败：保证 CI 入库提交不被阻断


def main():
    # —— 读 HTML（只读）——
    h = open(HTML, encoding='utf-8').read()
    dm = re.search(r'<script[^>]*id="data"[^>]*>(.*?)</script>', h, re.S)
    mm = re.search(r'<script[^>]*id="meta"[^>]*>(.*?)</script>', h, re.S)
    if not (dm and mm):
        soft_fail('HTML data/meta 块定位失败')
    rows, meta = json.loads(dm.group(1)), json.loads(mm.group(1))

    n = len(rows)
    fp = meta['完整性指纹']['全库指纹']
    date = meta.get('updatedAt', '')

    # —— 扩展区统计（通用区/教程区），规模行全量覆盖，防手写漂移 ——
    gm = re.search(r'<script[^>]*id="general"[^>]*>(.*?)</script>', h, re.S)
    tm = re.search(r'<script[^>]*id="tutorials"[^>]*>(.*?)</script>', h, re.S)
    try:
        gen = json.loads(gm.group(1)) if gm else []
        tut = json.loads(tm.group(1)) if tm else []
    except Exception:
        gen, tut = [], []
    gcat = Counter(x.get('cat', '未分类') for x in gen)
    gen_str = ' / '.join('%s %d' % (k, v) for k, v in gcat.most_common())

    # —— 统计 ——
    fam = Counter(d['model'] for d in rows)
    model_str = '、'.join('%s ×%d' % (k, v) for k, v in fam.most_common())
    stats_line = ('- 当前规模：**主库 %d 条**（%s）＋ **通用区 %d 条**（%s）＋ **教程区 %d 篇**，'
                  '合计 **%d 条 + %d 篇**｜ 版本标签 `%s` ｜ 主库全库指纹 `%s`') % (
        n, model_str, len(gen), gen_str, len(tut), n + len(gen), len(tut),
        meta.get('version'), fp)

    cats = OrderedDict()
    for d in rows:
        cats.setdefault(d['cat'], Counter())[d['sub']] += 1
    table = ['当前 %d 大类与子类（%d 条实况，%s）：' % (len(cats), n, date), '',
             '| 大类 | 条数 | 现有子类（条数） |', '|---|---|---|']
    for cat, subs in sorted(cats.items(), key=lambda x: (-sum(x[1].values()), x[0])):
        table.append('| %s | %d | %s |' % (
            cat, sum(subs.values()),
            '、'.join('%s(%d)' % (s, c) for s, c in subs.most_common())))
    table.append('')  # 保留表格与后文之间的空行（markdown 分段）

    # —— 读 README，行级手术 ——
    lines = open(README, encoding='utf-8').read().split('\n')

    # 1) 规模行
    i_stats = next((i for i, l in enumerate(lines) if l.startswith('- 当前规模：')), None)
    if i_stats is None:
        soft_fail('找不到「- 当前规模：」锚点行')
    m_old = re.search(r'\*\*(?:主库 )?(\d+) 条\*\*', lines[i_stats])
    if not m_old:
        soft_fail('规模行条数解析失败')
    old_n = int(m_old.group(1))
    lines[i_stats] = stats_line

    # 2) 分类实况表（标题行 + 空行 + 连续表格行）
    i_tbl = next((i for i, l in enumerate(lines)
                  if l.startswith('当前 ') and '大类与子类' in l and '条实况' in l), None)
    if i_tbl is None:
        soft_fail('找不到分类实况表标题行')
    j = i_tbl + 1
    while j < len(lines) and (lines[j].strip() == '' or lines[j].startswith('|')):
        j += 1
    lines[i_tbl:j] = table

    # 3) §12 变更记录（仅当条数变化时补一条；只追加，绝不改写历史条目）
    if old_n != n:
        if n < old_n:
            soft_fail('库条数(%d)少于 README 记载(%d)，疑似异常，不同步' % (n, old_n))
        i_log = next((i for i, l in enumerate(lines) if l.startswith('## 12')), None)
        if i_log is None:
            soft_fail('找不到「## 12. 变更记录」章节')
        k = i_log + 1
        while k < len(lines) and lines[k].strip() == '':
            k += 1
        entry = '- **%s（CI 自动同步）**：入库 %d 条（%d → %d；全库指纹 `%s`）；README 规模与分类实况表由 CI 自动更新。' % (
            date, n - old_n, old_n, n, fp)
        lines.insert(k, entry)
        print('✓ 变更记录 +1：%s' % entry)

    out = '\n'.join(lines)
    src = open(README, encoding='utf-8').read()
    if out == src:
        print('✓ README 已是现状（%d 条，指纹 %s），零改动' % (n, fp))
    else:
        open(README, 'w', encoding='utf-8').write(out)
        print('✓ README 已同步：%d 条（原 %d 条）｜ 指纹 %s ｜ 分类 %d 大类 / %d 子类' % (
            n, old_n, fp, len(cats), sum(len(c) for c in cats.values())))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        soft_fail('未预期异常 %r' % e)
