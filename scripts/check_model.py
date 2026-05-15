# TODO check used? if not, remove

import requests, sys
try:
    r = requests.get('http://localhost:11434/api/tags', timeout=10)
    target = sys.argv[1]
    for m in r.json().get('models', []):
        if target in str(m.get('name', '')):
            sys.exit(0)
    sys.exit(1)
except Exception:
    sys.exit(1)
