import os
import subprocess
import shutil

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
root_archive = os.path.join(repo_root, 'archive')
scripts_archive = os.path.join(repo_root, 'scripts', 'archive')

if not os.path.isdir(scripts_archive):
    print('No scripts/archive to merge.')
    raise SystemExit(0)

if not os.path.isdir(root_archive):
    os.makedirs(root_archive)

moved = []
for dirpath, dirnames, filenames in os.walk(scripts_archive, topdown=True):
    rel = os.path.relpath(dirpath, scripts_archive)
    target_dir = os.path.join(root_archive, rel) if rel != '.' else root_archive
    if not os.path.isdir(target_dir):
        os.makedirs(target_dir, exist_ok=True)
    for f in filenames:
        src = os.path.join(dirpath, f)
        dst = os.path.join(target_dir, f)
        # try git mv first
        try:
            subprocess.run(['git', 'mv', src, dst], check=True)
            moved.append(dst)
        except subprocess.CalledProcessError:
            # fallback to shutil.move
            try:
                shutil.move(src, dst)
                # if moved by shutil, stage the dst
                subprocess.run(['git', 'add', dst], check=False)
                moved.append(dst)
            except Exception as e:
                print('Failed to move', src, '->', dst, e)

# remove empty directories under scripts/archive
for dirpath, dirnames, filenames in os.walk(scripts_archive, topdown=False):
    try:
        if not os.listdir(dirpath):
            os.rmdir(dirpath)
    except Exception:
        pass

# remove scripts/archive if empty
if os.path.isdir(scripts_archive) and not os.listdir(scripts_archive):
    try:
        os.rmdir(scripts_archive)
        # stage removal
        subprocess.run(['git', 'add', '-A'], check=False)
    except Exception:
        pass

if moved:
    print('Moved files:')
    for m in moved:
        print(' -', m)
    # commit
    subprocess.run(['git', 'commit', '-m', 'chore: merge scripts/archive into root archive'], check=False)
else:
    print('No files moved.')
