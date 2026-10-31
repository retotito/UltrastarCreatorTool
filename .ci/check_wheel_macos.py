"""Fails if an installed wheel needs a newer macOS than the target: `check_wheel_macos.py <venv> <version>`."""
import glob
import re
import sys

venv, target = sys.argv[1], sys.argv[2]
limit = tuple(int(x) for x in target.split('.')[:2])
newer = []
for wheel in glob.glob(f'{venv}/**/*.dist-info/WHEEL', recursive=True):
    for line in open(wheel):
        m = re.match(r'Tag:\s*\S+-macosx_(\d+)_(\d+)_', line)
        if m and (int(m.group(1)), int(m.group(2))) > limit:
            newer.append(f'{wheel}: {line.strip()}')
for line in newer:
    print(line)
if newer:
    print(f'::error::wheels above for a newer macOS than {target}')
    sys.exit(1)
