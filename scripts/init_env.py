"""Create private development credentials; existing values are never printed or replaced."""
from pathlib import Path
import secrets
from urllib.parse import urlparse, unquote
from dotenv import dotenv_values

root=Path(__file__).resolve().parents[1]
path=root/'.env'
if not path.exists():
    text=(root/'.env.example').read_text(encoding='utf-8')
    text=text.replace('replace-locally',secrets.token_urlsafe(24)).replace('generate-a-local-random-secret',secrets.token_urlsafe(32))
    text=text.replace('DEMO_PASSWORD=\n','DEMO_PASSWORD='+secrets.token_urlsafe(18)+'\n')
    path.write_text(text,encoding='utf-8')
values=dotenv_values(path)
additions={
    'PG_ADMIN_PASSWORD':secrets.token_urlsafe(24),
    'PG_APP_PASSWORD':unquote(urlparse(values['DATABASE_URL'].replace('postgresql+asyncpg','postgresql')).password),
    'PG_MOCK_PASSWORD':unquote(urlparse(values['MOCK_DATABASE_URL'].replace('postgresql+asyncpg','postgresql')).password),
}
lines=path.read_text(encoding='utf-8').splitlines()
for key,value in additions.items():
    if not values.get(key):
        lines=[line for line in lines if not line.startswith(key+'=')]
        lines.append(key+'='+value)
path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Private .env prepared. Read the login credential locally; do not paste it into chat or Git.')
