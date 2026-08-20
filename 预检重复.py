#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 预检重复.py —— 追加前剔除与库内完全重复的原文条目，避免整批被拒
import re, json, sys
h = open('视频提示词库-多模型.html', encoding='utf-8').read()
data = None
for m in re.finditer(r'(<script[^>]*id="data"[^>]*>)(.*?)(</script>)', h, re.S):
    body = m.group(2)
    if body.lstrip()[:1] == '[':
        try:
            data = json.loads(body)
            break
        except Exception:
            pass
have = {d['original'] for d in data}
items = json.load(open('新条目.json', encoding='utf-8'))
keep = [x for x in items if x['original'] not in have]
drop = len(items) - len(keep)
print('库内重复剔除: %d 条, 剩余: %d 条' % (drop, len(keep)))
if not keep:
    print('NOTHING TO APPEND')
    sys.exit(3)
json.dump(keep, open('新条目.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
