"""Migrate and seed only the dedicated test database; optionally serve its HTTP Mock."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--serve-mock', action='store_true')
args = parser.parse_args()
env = {**dotenv_values(root / '.env'), **os.environ}
for key in ('TEST_DATABASE_URL', 'MOCK_TEST_DATABASE_URL'):
    if urlparse(env.get(key, '')).path != '/erp_phase1_test':
        raise SystemExit(f'{key} must name erp_phase1_test')
env.update(APP_ENV='test', AI_MODE='offline', DEEPSEEK_API_KEY='',
    DATABASE_URL=env['TEST_DATABASE_URL'], MOCK_DATABASE_URL=env['MOCK_TEST_DATABASE_URL'])
for folder in ('backend', 'mock_boss'):
    for module, arguments in [('alembic', ['upgrade', 'head']), ('app.seed', ['--demo'])]:
        subprocess.run([sys.executable, '-m', module, *arguments], cwd=root / folder, env=env, check=True)
print('Dedicated test database prepared; existing records preserved.')
if args.serve_mock:
    subprocess.run([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8002', '--no-access-log'],
        cwd=root / 'mock_boss', env=env, check=True)
