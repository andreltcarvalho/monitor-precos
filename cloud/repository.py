"""Data API com JWT do usuário; não usa segredo administrativo."""
import asyncio
import os

from fastapi import HTTPException

from core import utcnow


def configuration():
    url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    key = os.environ.get('SUPABASE_PUBLISHABLE_KEY', '')
    if not url or not key:
        raise HTTPException(503, 'Supabase ainda não configurado no servidor.')
    return url, key


class Repository:
    def __init__(self, client, token, owner):
        self.client, self.token, self.owner = client, token, owner
        self.url, key = configuration()
        self.headers = {'apikey': key, 'Authorization': 'Bearer ' + token}

    async def request(self, method, path, *, params=None, data=None, prefer=None):
        headers = dict(self.headers)
        if prefer:
            headers['Prefer'] = prefer
        response = await self.client.request(method, self.url + '/rest/v1/' + path,
                                             params=params, json=data, headers=headers)
        if response.status_code in (401, 403):
            raise HTTPException(401, 'Sessão expirada. Entre novamente.')
        if response.is_error:
            raise HTTPException(502, 'Não foi possível acessar os dados no Supabase.')
        return response.json() if response.content else None

    async def records(self, kind, *, limit=10000):
        rows = []
        while len(rows) < limit:
            page_size = min(500, limit-len(rows))
            batch = await self.request('GET', 'monitor_records', params={
                'owner_id': 'eq.' + self.owner, 'kind': 'eq.' + kind,
                'select': 'record_key,data,updated_at', 'order': 'record_key',
                'offset': len(rows), 'limit': page_size})
            rows.extend(batch)
            if len(batch) < page_size:
                break
        return rows

    async def get(self, kind, key):
        rows = await self.request('GET', 'monitor_records', params={
            'owner_id': 'eq.' + self.owner, 'kind': 'eq.' + kind,
            'record_key': 'eq.' + str(key), 'select': 'data', 'limit': 1})
        return rows[0]['data'] if rows else None

    async def put(self, kind, key, data):
        await self.put_many([{'kind': kind, 'record_key': str(key), 'data': data}])

    async def put_many(self, rows):
        if not rows:
            return
        values = [dict(row, owner_id=self.owner, updated_at=utcnow()) for row in rows]
        await self.request('POST', 'monitor_records', params={'on_conflict': 'owner_id,kind,record_key'},
                           data=values, prefer='resolution=merge-duplicates')

    async def delete(self, kind, key):
        await self.request('DELETE', 'monitor_records', params={
            'owner_id': 'eq.' + self.owner, 'kind': 'eq.' + kind, 'record_key': 'eq.' + str(key)})

    async def command(self, action, payload):
        rows = await self.request('POST', 'monitor_commands',
            data={'owner_id': self.owner, 'action': action, 'payload': payload}, prefer='return=representation')
        return rows[0]

    async def history(self, component, since_day):
        return await self.request('POST', 'rpc/monitor_recent_observations',
                                  data={'component_key': str(component), 'since_day': since_day})

    async def commands(self):
        pending, history = await asyncio.gather(
            self.request('GET', 'monitor_commands', params={
                'owner_id': 'eq.' + self.owner, 'status': 'in.(pending,running)',
                'select': '*', 'order': 'created_at.asc', 'limit': 500}),
            self.request('GET', 'monitor_commands', params={
                'owner_id': 'eq.' + self.owner, 'status': 'in.(done,failed)',
                'select': '*', 'order': 'created_at.desc', 'limit': 50}))
        return pending + history


async def user_session(client, token):
    if not token or len(token) > 8192:
        raise HTTPException(401, 'Entre para acessar seu monitor.')
    url, key = configuration()
    response = await client.get(url + '/auth/v1/user', headers={'apikey': key, 'Authorization': 'Bearer ' + token})
    if response.status_code in (401, 403):
        raise HTTPException(401, 'Sessão expirada. Entre novamente.')
    if response.is_error:
        raise HTTPException(502, 'Não foi possível validar a sessão.')
    user = response.json()
    if not user.get('id') or user.get('is_anonymous'):
        raise HTTPException(401, 'Entre com uma conta confirmada.')
    return user
