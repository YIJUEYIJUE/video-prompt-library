#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 勘误更新.py —— 单条原文修正 / 勘误登记 专用工具
# （补齐"只追加"之外的第二条合法写入路径，替代手工编辑 data/meta 块）
#
# 用法：
#   # 修正单条原文（新原文来自 txt/json 文件；json 含 original 字段则取之）
#   python 勘误更新.py fix <库.html> <条目id> <新原文文件> --类型 OCR修正 --详情 "..."
#   # 仅登记勘误（原文不动，供存疑溯源）
#   python 勘误更新.py note <库.html> <id1,id2,...> --类型 OCR修正 --详情 "..."
#   通用选项：--dry-run 预览不写库
#
# 行为（fix）：备份 → 更新条目 original/chars/sha1 → 重算逐条+全库指纹
#              → 勘误登记 + 变更日志 → check_library 全量校验(fail-closed) → save → 自检
#              → 刷新 AI 静态导出 → 提示 README 同步
# 原则：原文一个字都不能被本工具之外的路径改动；本工具的每次改动必须留下勘误登记。
import sys, os, json, hashlib, datetime, shutil, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 追加提示词 import load, save, sha, check, _refresh_ai_exports
from 库共享定义 import ERR_TYPES

BAKDIR = '视频提示词库_备份'


def read_new_text(path):
    """txt = 整个文件即原文（仅去首尾空行）；json = 取 original 字段。"""
    raw = open(path, encoding='utf-8').read()
    if path.lower().endswith('.json'):
        arr = json.loads(raw)
        if isinstance(arr, list):
            assert len(arr) == 1, 'json 为多条，请给单条'
            arr = arr[0]
        assert 'original' in arr, 'json 缺 original 字段'
        return arr['original'].rstrip('\n')
    return raw.strip('\n')


def recompute_fp(data, meta):
    per = {d['id']: sha(d['original']) for d in data}
    meta['完整性指纹'] = {
        '条目数': len(data),
        '原文总字数': sum(len(d['original']) for d in data),
        '全库指纹': hashlib.sha256(''.join(per[k] for k in sorted(per)).encode()).hexdigest()[:16],
        '逐条指纹': per}
    return meta


def do_fix(h, data, meta, args):
    d = next((x for x in data if x['id'] == args.id), None)
    if d is None:
        sys.exit('× 条目不存在: %s' % args.id)
    new = read_new_text(args.newfile)
    old = d['original']
    if new == old:
        sys.exit('· 新原文与现库一致，无需更新')
    k = 0
    while k < min(len(old), len(new)) and old[k] == new[k]:
        k += 1
    print('〔预览〕%s《%s》 %d字 → %d字' % (args.id, d.get('name', '?'), len(old), len(new)))
    print('  首差异@%d  旧: …%r' % (k, old[max(0, k - 25):k + 45]))
    print('            新: …%r' % (new[max(0, k - 25):k + 45],))
    if args.dry_run:
        print('〔dry-run〕未写库')
        return
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    os.makedirs(BAKDIR, exist_ok=True)
    shutil.copy2(args.html, os.path.join(BAKDIR, ts + '__' + os.path.basename(args.html)))
    d['original'] = new
    d['chars'] = len(new)
    d['sha1'] = sha(new)  # 与 meta 逐条指纹同算法，顺带收敛历史遗留字段
    recompute_fp(data, meta)
    today = datetime.date.today().isoformat()
    meta.setdefault('勘误登记', []).append({
        '日期': today, '条目': [args.id], '类型': args.类型, '详情': args.详情, 'commit': 'local'})
    meta.setdefault('变更日志', []).append({
        '日期': today,
        '内容': '勘误更新 %s（%d→%d 字，%s），版本标签保持 %s' % (args.id, len(old), len(new), args.详情, meta.get('version'))})
    meta['updatedAt'] = today
    before = {x['id']: x['original'] for x in data}
    bad = check(data, meta)
    if bad:
        print('× 校验未通过，未写出任何文件：')
        for b in bad[:30]:
            print('   ', b[0], b[1])
        sys.exit(1)
    save(h, data, meta, args.html)
    _, d2, m2 = load(args.html)
    assert len(d2) == len(data), '条目数对不上'
    assert all(x['original'] == before[x['id']] for x in d2 if x['id'] != args.id), '!! 其他条目原文被改动'
    assert next(x for x in d2 if x['id'] == args.id)['original'] == new, '!! 新原文写入不符'
    _refresh_ai_exports(args.html)
    print('✓ 勘误更新 %s：%d→%d 字；新全库指纹 %s（README 同步请跑 同步README统计.py）'
          % (args.id, len(old), len(new), m2['完整性指纹']['全库指纹']))


def do_note(h, data, meta, args):
    ids = [x.strip() for x in args.ids.split(',') if x.strip()]
    have = {d['id'] for d in data}
    miss = [i for i in ids if i not in have]
    if miss:
        sys.exit('× 条目不存在: %s' % ','.join(miss))
    if args.dry_run:
        print('〔dry-run〕将登记 %s（%s）：%s' % (ids, args.类型, args.详情))
        return
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    os.makedirs(BAKDIR, exist_ok=True)
    shutil.copy2(args.html, os.path.join(BAKDIR, ts + '__' + os.path.basename(args.html)))
    recompute_fp(data, meta)  # 原文未动，重算应与登记一致（自洽确认）
    today = datetime.date.today().isoformat()
    meta.setdefault('勘误登记', []).append({
        '日期': today, '条目': ids, '类型': args.类型, '详情': args.详情, 'commit': 'local'})
    meta['updatedAt'] = today
    bad = check(data, meta)
    if bad:
        print('× 校验未通过，未写出任何文件：')
        for b in bad[:30]:
            print('   ', b[0], b[1])
        sys.exit(1)
    save(h, data, meta, args.html)
    _, d2, m2 = load(args.html)
    assert len(d2) == len(data)
    assert all(x['original'] == next(y for y in data if y['id'] == x['id'])['original'] for x in d2), '!! 原文被改动'
    print('✓ 勘误登记 %s（%s）；全库指纹不变 %s'
          % (','.join(ids), args.类型, m2['完整性指纹']['全库指纹']))


def main():
    p = argparse.ArgumentParser(description='单条原文修正 / 勘误登记（合法写入路径，禁手工编辑 data/meta）')
    sub = p.add_subparsers(dest='cmd', required=True)

    pf = sub.add_parser('fix', help='修正单条原文')
    pf.add_argument('html'), pf.add_argument('id'), pf.add_argument('newfile')
    pn = sub.add_parser('note', help='仅登记勘误（原文不动）')
    pn.add_argument('html'), pn.add_argument('ids')
    for s in (pf, pn):
        s.add_argument('--类型', default='OCR修正', choices=sorted(ERR_TYPES))
        s.add_argument('--详情', required=True)
        s.add_argument('--dry-run', action='store_true')
    a = p.parse_args()

    h, data, meta = load(a.html)
    if not data:
        sys.exit('× 数据块为空')
    if a.cmd == 'fix':
        do_fix(h, data, meta, a)
    else:
        do_note(h, data, meta, a)


if __name__ == '__main__':
    main()
