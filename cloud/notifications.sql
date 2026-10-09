-- Bot pessoal: segredo no Vault, configurações e entregas em schema privado.
create table if not exists monitor_private.telegram_connections (
  owner_id uuid primary key references auth.users(id) on delete cascade,
  secret_id uuid not null, username text not null, chat_id text,
  nonce text not null, paired_at timestamptz not null default now(),
  pair_until timestamptz not null default now()+interval '15 minutes',
  enabled boolean not null default false, revision uuid not null default gen_random_uuid(),
  detail text not null default '', evaluation_id bigint, evaluated_at timestamptz,
  constraint telegram_recipient_private check(chat_id is null or chat_id ~ '^[0-9]{1,20}$')
);
create table if not exists monitor_private.telegram_deliveries (
  owner_id uuid not null references auth.users(id) on delete cascade,
  identity text not null, price bigint not null check(price>0), payload jsonb not null,
  revision uuid not null, state text not null default 'pending'
    check(state in ('pending','sending','sent','failed','uncertain','cancelled')),
  request_id bigint, attempted_at timestamptz, attempts integer not null default 0,
  retry_at timestamptz, detail text not null default '',
  primary key(owner_id,identity,price)
);
alter table monitor_private.telegram_connections enable row level security;
alter table monitor_private.telegram_deliveries enable row level security;
revoke all on monitor_private.telegram_connections, monitor_private.telegram_deliveries from public, anon, authenticated;

-- A sessão só obtém o segredo do seu próprio bot, usado pela API autenticada.
create or replace function public.monitor_telegram_config() returns jsonb
language plpgsql security definer set search_path='' as $$
declare result jsonb;
begin
  if auth.uid() is null then raise insufficient_privilege; end if;
  select jsonb_build_object('token',s.decrypted_secret,'username',c.username,'chat_id',c.chat_id,
    'nonce',c.nonce,'paired_at',c.paired_at,'pair_until',c.pair_until,'enabled',c.enabled,'detail',c.detail)
    into result from monitor_private.telegram_connections c join vault.decrypted_secrets s on s.id=c.secret_id
    where c.owner_id=auth.uid();
  return coalesce(result,'{}');
end;
$$;
create or replace function public.monitor_telegram_save(bot_token text,bot_username text) returns void
language plpgsql security definer set search_path='' as $$
declare secret uuid;
begin
  if auth.uid() is null then raise insufficient_privilege; end if;
  if bot_token !~ '^[0-9]{5,15}:[A-Za-z0-9_-]{20,100}$' or bot_username !~ '^[A-Za-z0-9_]{5,64}$' then
    raise invalid_parameter_value; end if;
  perform pg_advisory_xact_lock(hashtext(auth.uid()::text||'telegram-config'));
  select secret_id into secret from monitor_private.telegram_connections where owner_id=auth.uid() for update;
  if secret is null then
    secret := vault.create_secret(bot_token,'monitor_telegram_'||auth.uid()::text,'Bot pessoal do monitor');
  else
    perform vault.update_secret(secret,bot_token);
  end if;
  insert into monitor_private.telegram_connections(owner_id,secret_id,username,nonce)
    values(auth.uid(),secret,bot_username,replace(gen_random_uuid()::text,'-',''))
    on conflict(owner_id) do update set secret_id=excluded.secret_id,username=excluded.username,
      chat_id=null,nonce=excluded.nonce,paired_at=now(),pair_until=now()+interval '15 minutes',
      enabled=false,revision=gen_random_uuid(),detail='',evaluation_id=null;
end;
$$;
create or replace function public.monitor_telegram_recipient(pair_nonce text,recipient_id text) returns void
language plpgsql security definer set search_path='' as $$
begin
  if auth.uid() is null then raise insufficient_privilege; end if;
  if recipient_id !~ '^[0-9]{1,20}$' then raise invalid_parameter_value; end if;
  update monitor_private.telegram_connections set chat_id=recipient_id,enabled=true,detail='',
    pair_until=now(),revision=gen_random_uuid()
    where owner_id=auth.uid() and nonce=pair_nonce and pair_until>now();
  if not found then raise invalid_parameter_value using message='Link de conexão expirado.'; end if;
end;
$$;
create or replace function public.monitor_telegram_toggle(is_enabled boolean) returns void
language plpgsql security definer set search_path='' as $$
begin
  if auth.uid() is null then raise insufficient_privilege; end if;
  update monitor_private.telegram_connections set enabled=is_enabled,revision=gen_random_uuid(),detail=''
    where owner_id=auth.uid() and chat_id is not null;
  if not found then raise invalid_parameter_value; end if;
end;
$$;
revoke all on function public.monitor_telegram_config(), public.monitor_telegram_save(text,text),
  public.monitor_telegram_recipient(text,text), public.monitor_telegram_toggle(boolean) from public,anon;
grant execute on function public.monitor_telegram_config(), public.monitor_telegram_save(text,text),
  public.monitor_telegram_recipient(text,text), public.monitor_telegram_toggle(boolean) to authenticated;

create or replace function monitor_private.dispatch_telegram_notifications() returns integer
language plpgsql set search_path='' as $$
declare conn record; delivery record; response record; row jsonb; body jsonb; part jsonb; offer jsonb;
  secret text; endpoint text; token text; request bigint; count integer:=0; parts jsonb; offers jsonb; receipts jsonb; settings jsonb;
begin
  if not pg_try_advisory_xact_lock(hashtext('monitor-telegram-dispatch')) then return 0; end if;
  -- Uma resposta ausente não prova que o Telegram deixou de entregar. Nunca repetir às cegas.
  for delivery in select * from monitor_private.telegram_deliveries where state='sending' loop
    select * into response from net._http_response where id=delivery.request_id;
    if not found then
      if delivery.attempted_at<now()-interval '3 minutes' then
        update monitor_private.telegram_deliveries set state='uncertain',detail='Entrega sem confirmação; reenvio automático bloqueado.'
          where owner_id=delivery.owner_id and identity=delivery.identity and price=delivery.price;
      end if;
      continue;
    end if;
    begin body:=response.content::jsonb; exception when others then body:='{}'; end;
    if body->>'ok'='true' then
      update monitor_private.telegram_deliveries set state='sent',detail='Enviado.'
        where owner_id=delivery.owner_id and identity=delivery.identity and price=delivery.price;
      update monitor_private.telegram_connections set detail='Último aviso enviado.' where owner_id=delivery.owner_id;
    elsif body->>'ok'='false' and (body->>'error_code') in ('429','500','502','503','504') then
      update monitor_private.telegram_deliveries set state='failed',
        retry_at=now()+make_interval(secs=>greatest(300,least(86400,coalesce((body#>>'{parameters,retry_after}')::integer,300)))),
        detail='Telegram pediu uma pausa; nova tentativa agendada.'
        where owner_id=delivery.owner_id and identity=delivery.identity and price=delivery.price;
    else
      update monitor_private.telegram_deliveries set state=case when body->>'ok'='false' then 'failed' else 'uncertain' end,
        detail='Entrega não confirmada; confira a conexão do bot.'
        where owner_id=delivery.owner_id and identity=delivery.identity and price=delivery.price;
      update monitor_private.telegram_connections set detail='Telegram recusou ou não confirmou o aviso. Use Enviar teste para conferir a conexão.',
        enabled=case when body->>'error_code' in ('401','403') then false else enabled end where owner_id=delivery.owner_id;
    end if;
  end loop;
  for conn in select * from monitor_private.telegram_connections where evaluation_id is not null loop
    select * into response from net._http_response where id=conn.evaluation_id;
    if not found then
      if conn.evaluated_at<now()-interval '3 minutes' then
        update monitor_private.telegram_connections set evaluation_id=null,detail='Avaliação de alertas indisponível; nova tentativa automática.' where owner_id=conn.owner_id;
      end if;
      continue;
    end if;
    begin body:=response.content::jsonb; exception when others then body:='{}'; end;
    if response.status_code=200 and jsonb_typeof(body->'notifications')='array' and conn.enabled then
      for row in select value from jsonb_array_elements(body->'notifications') limit 100 loop
        if row->>'identity' !~ '^[a-f0-9]{64}$' or row->>'price' !~ '^[0-9]{1,12}$' then continue; end if;
        insert into monitor_private.telegram_deliveries(owner_id,identity,price,payload,revision)
          values(conn.owner_id,row->>'identity',(row->>'price')::bigint,row,conn.revision)
          on conflict(owner_id,identity,price) do update set payload=excluded.payload,revision=excluded.revision,state='pending'
            where telegram_deliveries.state='cancelled';
      end loop;
    elsif response.status_code<>200 then
      update monitor_private.telegram_connections set detail='Avaliação de alertas indisponível; nova tentativa automática.' where owner_id=conn.owner_id;
    end if;
    update monitor_private.telegram_connections set evaluation_id=null where owner_id=conn.owner_id;
  end loop;
  -- Revalidar o cadastro, a leitura e as preferências antes de cada envio.
  for conn in select * from monitor_private.telegram_connections where enabled and chat_id is not null loop
    for delivery in select * from monitor_private.telegram_deliveries d where d.owner_id=conn.owner_id
      and (state='pending' or (state='failed' and attempts<3 and retry_at<=now())) order by price,identity loop
      select c.data || coalesce(o.data,'{}') into part from public.monitor_records c
        left join public.monitor_records o on o.owner_id=c.owner_id and o.kind='overrides' and o.record_key='component:'||c.record_key
        where c.owner_id=conn.owner_id and c.kind='components' and c.record_key=delivery.payload->>'component_key';
      select r.data || coalesce(p.data,'{}') into offer from public.monitor_records r
        left join public.monitor_records p on p.owner_id=r.owner_id and p.kind='preferences' and p.record_key=r.record_key
        where r.owner_id=conn.owner_id and r.kind='offers' and r.record_key=delivery.payload->>'offer_id';
      if part is null or offer is null or delivery.revision<>conn.revision
        or part is distinct from delivery.payload->'component' or offer is distinct from delivery.payload->'reading'
        or coalesce((select coalesce(o.data->>'value',s.data->>'value') from public.monitor_records s
          left join public.monitor_records o on o.owner_id=s.owner_id and o.kind='overrides' and o.record_key=s.record_key
          where s.owner_id=conn.owner_id and s.kind='settings' and s.record_key='shop:'||(offer->>'shop')),
          (select data->>'value' from public.monitor_records where owner_id=conn.owner_id and kind='overrides' and record_key='shop:'||(offer->>'shop')),'1')<>'1'
        or exists(select 1 from monitor_private.telegram_deliveries previous where previous.owner_id=conn.owner_id
          and previous.identity=delivery.identity and previous.price<=delivery.price and previous.state in ('sent','sending','uncertain'))
        or coalesce(part->>'enabled','0') not in ('1','true') or coalesce(part->>'deleted','false')='true'
        or part->'notification_target' is distinct from delivery.payload->'threshold'
        or offer->'checked_at' is distinct from delivery.payload->'checked_at'
        or coalesce(offer->>'hidden','false')='true' or offer->>'availability'='out'
        or (delivery.payload->>'valid_until')::timestamptz<=now() then
        update monitor_private.telegram_deliveries set state='cancelled' where owner_id=delivery.owner_id and identity=delivery.identity and price=delivery.price;
        continue;
      end if;
      select decrypted_secret into token from vault.decrypted_secrets where id=conn.secret_id;
      request:=net.http_post(url:='https://api.telegram.org/bot'||token||'/sendMessage',
        body:=jsonb_build_object('chat_id',conn.chat_id,'text',delivery.payload->>'text','link_preview_options',jsonb_build_object('is_disabled',true)),
        headers:='{"Content-Type":"application/json"}'::jsonb,timeout_milliseconds:=15000);
      update monitor_private.telegram_deliveries set state='sending',request_id=request,attempted_at=now(),attempts=attempts+1
        where owner_id=delivery.owner_id and identity=delivery.identity and price=delivery.price;
      count:=count+1;
      exit; -- No máximo um aviso por conta/minuto, sem rajadas.
    end loop;
  end loop;
  select decrypted_secret into secret from vault.decrypted_secrets where name='monitor_cloud_cron_secret';
  select regexp_replace(decrypted_secret,'/api/scheduled/collect$','/api/scheduled/notifications') into endpoint
    from vault.decrypted_secrets where name='monitor_cloud_cron_url';
  if secret is null or endpoint is null then return count; end if;
  for conn in select * from monitor_private.telegram_connections where enabled and chat_id is not null and evaluation_id is null loop
    select coalesce(jsonb_agg(c.data||coalesce(o.data,'{}')),'[]') into parts from public.monitor_records c
      left join public.monitor_records o on o.owner_id=c.owner_id and o.kind='overrides' and o.record_key='component:'||c.record_key
      where c.owner_id=conn.owner_id and c.kind='components'
        and coalesce((c.data||coalesce(o.data,'{}'))->>'deleted','false')<>'true';
    if not exists(select 1 from jsonb_array_elements(parts) p where jsonb_typeof(p->'notification_target')='number' and coalesce(p->>'enabled','0') in ('1','true')) then continue; end if;
    select coalesce(jsonb_agg(r.data||coalesce(p.data,'{}')),'[]') into offers from public.monitor_records r
      left join public.monitor_records p on p.owner_id=r.owner_id and p.kind='preferences' and p.record_key=r.record_key
      where r.owner_id=conn.owner_id and r.kind='offers';
    select coalesce(jsonb_agg(jsonb_build_object('identity',identity,'price',price)),'[]') into receipts
      from (select identity,min(price) price from monitor_private.telegram_deliveries
        where owner_id=conn.owner_id and state in ('sent','sending','uncertain') group by identity) sent;
    select coalesce(jsonb_object_agg(s.record_key,coalesce(o.data->>'value',s.data->>'value','1')),'{}') into settings from public.monitor_records s
      left join public.monitor_records o on o.owner_id=s.owner_id and o.kind='overrides' and o.record_key=s.record_key
      where s.owner_id=conn.owner_id and s.kind='settings' and s.record_key like 'shop:%';
    request:=net.http_post(url:=endpoint,body:=jsonb_build_object('components',parts,'offers',offers,'receipts',receipts,'settings',settings),
      headers:=jsonb_build_object('Content-Type','application/json','Authorization','Bearer '||secret),timeout_milliseconds:=20000);
    update monitor_private.telegram_connections set evaluation_id=request,evaluated_at=now() where owner_id=conn.owner_id;
  end loop;
  return count;
end;
$$;
revoke all on function monitor_private.dispatch_telegram_notifications() from public,anon,authenticated;
-- Ativar depois de validar o deploy:
-- select cron.schedule('monitor-precos-telegram-alerts','* * * * *','select monitor_private.dispatch_telegram_notifications();');
