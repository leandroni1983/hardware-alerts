import os

root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
matches = []
for dirpath, dirnames, filenames in os.walk(root):
    for d in list(dirnames):
        if d.lower() == 'archive':
            matches.append(os.path.join(dirpath, d))
            # skip descending into this archive to avoid duplicates
            dirnames.remove(d)

if not matches:
    print('No archive directories found')
else:
    for m in matches:
        print(m)
