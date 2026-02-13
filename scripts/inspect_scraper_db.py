path = r'd:\Leandro\docker\hardware-alerts\storage\scraper_db.py'
with open(path, 'r', encoding='utf-8') as f:
    s = f.read()
print('Length:', len(s))
print('Triple quotes count:', s.count('"""'))
lines = s.splitlines()
for i, line in enumerate(lines, start=1):
    if i<=300:
        print(f'{i:04d}: {line}')
    else:
        break
