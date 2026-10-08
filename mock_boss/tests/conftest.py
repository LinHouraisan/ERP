import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import make_url

load_dotenv(Path(__file__).resolve().parents[2]/'.env')
os.environ['MOCK_DATABASE_URL'] = os.environ['MOCK_TEST_DATABASE_URL']
os.environ['APP_ENV'] = 'test'
url = make_url(os.environ['MOCK_DATABASE_URL'])
if url.drivername != 'postgresql+asyncpg' or not url.database.startswith('erp_') or not url.database.endswith('_test'):
    raise RuntimeError('Mock tests require a dedicated PostgreSQL erp_*_test database')
