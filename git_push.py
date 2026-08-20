# -*- coding: utf-8 -*-
"""git_push.py — 入库后自动推送到 GitHub（读取 .gh_token，不弹窗）"""
import subprocess, sys, os

ROOT = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(ROOT, '.gh_token')
REMOTE = 'https://github.com/YIJUEYIJUE/video-prompt-library.git'

def run(cmd, **kw):
    r = subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True, **kw)
    return r

def main():
    # 1. 读 token
    if not os.path.exists(TOKEN_FILE):
        print('× 找不到 .gh_token 文件，无法推送')
        sys.exit(1)
    token = open(TOKEN_FILE).read().strip()
    if not token:
        print('× .gh_token 为空')
        sys.exit(1)

    # 2. git status（只跟踪已入库的文件）
    tracked = ['视频提示词库-多模型-191条-V1.1.html', '提示词库说明.md',
               '库维护工具.py', '追加提示词.py', '.gitignore',
               'git_push.py', 'index.html', '.nojekyll']
    files_to_add = [f for f in tracked if os.path.exists(os.path.join(ROOT, f))]
    if not files_to_add:
        print('没有需要提交的文件')
        sys.exit(0)

    # 3. 检查是否有变更
    st = run('git status --porcelain')
    if not st.stdout.strip():
        print('工作区干净，无需推送')
        sys.exit(0)

    # 4. add + commit
    msg = sys.argv[1] if len(sys.argv) > 1 else '更新提示词库'
    run(f'git add {" ".join(files_to_add)}')
    c = run(f'git commit -m "{msg}"')
    if c.returncode != 0:
        print('× commit 失败:', c.stderr.strip())
        sys.exit(1)
    print(c.stdout.strip() or '(committed)')

    # 5. push（用 embedded token URL）
    url = f'https://YIJUEYIJUE:{token}@github.com/YIJUEYIJUE/video-prompt-library.git'
    p = run(f'git push {url} main:main')
    if p.returncode == 0:
        lines = [l for l in (p.stdout + p.stderr).strip().split('\n') if l]
        print('✓ 推送成功:', lines[-1] if lines else 'OK')
    else:
        print('× 推送失败:', (p.stderr or p.stdout).strip())
        sys.exit(1)

if __name__ == '__main__':
    main()
