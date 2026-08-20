#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 提取分类.py —— 从库 HTML 提取 cat/sub/model/tags 清单，供新条目归类参考
import re, json, collections
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
out = []
c = collections.Counter((d['cat'], d['sub']) for d in data)
out.append('== cat|sub|count ==')
out += ['%s|%s|%d' % (k[0], k[1], v) for k, v in sorted(c.items())]
out.append('== model|count ==')
mc = collections.Counter(d['model'] for d in data)
out += ['%s|%d' % kv for kv in sorted(mc.items())]
tc = collections.Counter(t for d in data for t in d.get('tags', []))
out.append('== top tags ==')
out.append(' '.join('%s:%d' % kv for kv in tc.most_common(100)))
out.append('== total %d ==' % len(data))
open('分类清单.txt', 'w', encoding='utf-8').write('\n'.join(out))
print('ok', len(data))
