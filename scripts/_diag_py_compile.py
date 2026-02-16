import os,py_compile,traceback
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
report_path = os.path.join(root, 'tmp_compile_report.txt')
errors = []
for dirpath, dirnames, filenames in os.walk(root):
    if any(part in ('.git','__pycache__','venv','env') for part in dirpath.split(os.sep)):
        continue
    for f in filenames:
        if not f.endswith('.py'):
            continue
        p = os.path.join(dirpath, f)
        try:
            py_compile.compile(p, doraise=True)
        except Exception as e:
            tb = traceback.format_exc()
            errors.append({'file': p, 'error': str(e), 'traceback': tb})

with open(report_path, 'w', encoding='utf-8') as outf:
    if not errors:
        outf.write('PY_COMPILE_OK: no syntax errors found\n')
    else:
        outf.write('PY_COMPILE_ERRORS: %d\n' % len(errors))
        for e in errors:
            outf.write('FILE: %s\n' % e['file'])
            outf.write(e['error'] + '\n')
            outf.write(e['traceback'] + '\n')
            outf.write('---\n')
print('WROTE', report_path)
