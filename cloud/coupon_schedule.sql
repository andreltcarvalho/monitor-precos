-- Aplicar após schedule.sql. Usa o mesmo Vault e Supabase Cron das ofertas.
create table monitor_private.coupon_jobs (
  owner_id uuid primary key references auth.users(id) on delete cascade,
  state text not null default 'idle' check (state in ('idle','running','done','failed')),
  attempted_at timestamptz,
  finished_at timestamptz,
  request_id bigint,
  detail text not null default ''
);
revoke all on monitor_private.coupon_jobs from public,anon,authenticated;

create function monitor_private.finish_coupon_jobs() returns integer
language plpgsql security invoker set search_path = '' as $$
declare
  job monitor_private.coupon_jobs%rowtype;
  response net._http_response%rowtype;
  result jsonb;
  item jsonb;
  failure text;
  finished integer := 0;
begin
  for job in select j.* from monitor_private.coupon_jobs j
    where j.state='running' and (j.attempted_at<now()-interval '2 minutes'
      or exists(select 1 from net._http_response r where r.id=j.request_id))
    for update of j skip locked
  loop
    failure := null;
    result := null;
    select * into response from net._http_response where id=job.request_id;
    if not found or response.timed_out then
      failure := 'Tempo limite da busca pública; última leitura preservada.';
    elsif response.error_msg is not null or response.status_code is distinct from 200 then
      failure := 'Busca pública indisponível; última leitura preservada.';
    else
      begin
        result := response.content::jsonb;
        if jsonb_typeof(result->'coupons') is distinct from 'array'
          or jsonb_array_length(result->'coupons')>500
          or jsonb_typeof(result->'status') is distinct from 'array'
          or jsonb_array_length(result->'status')<>3
          or (select count(distinct value->>'source') from jsonb_array_elements(result->'status'))<>3 then
          raise exception 'Resposta inválida';
        end if;
        for item in select value from jsonb_array_elements(result->'coupons') loop
          if jsonb_typeof(item) is distinct from 'object'
            or coalesce(item->>'source','') not in ('Pichau','Melhores Cartões','Pelando')
            or length(coalesce(item->>'code',''))>100 then raise exception 'Cupom inválido'; end if;
        end loop;
        for item in select value from jsonb_array_elements(result->'status') loop
          if jsonb_typeof(item) is distinct from 'object'
            or coalesce(item->>'source','') not in ('Pichau','Melhores Cartões','Pelando')
            or item->>'coupon_source' is distinct from 'true'
            or jsonb_typeof(item->'checked_at') is distinct from 'string' then
            raise exception 'Estado inválido';
          end if;
          insert into public.monitor_records(owner_id,kind,record_key,data)
            values(job.owner_id,'status','cloud:coupons:'||(item->>'source'),item)
            on conflict(owner_id,kind,record_key) do update set data=excluded.data,updated_at=now()
            where public.monitor_records.updated_at<=job.attempted_at;
        end loop;
        insert into public.monitor_records(owner_id,kind,record_key,data)
          values(job.owner_id,'settings','cloud_coupon_feed',jsonb_build_object('value',(result->'coupons')::text))
          on conflict(owner_id,kind,record_key) do update set data=excluded.data,updated_at=now()
          where public.monitor_records.updated_at<=job.attempted_at;
        if not exists(select 1 from jsonb_array_elements(result->'status') s where s->>'failures'='0') then
          failure := 'As fontes não concluíram a busca pública; última leitura preservada.';
        end if;
      exception when others then failure := 'Resposta pública inválida; última leitura preservada.';
      end;
    end if;
    update monitor_private.coupon_jobs set state=case when failure is null then 'done' else 'failed' end,
      finished_at=now(),detail=coalesce(failure,'Busca pública concluída.') where owner_id=job.owner_id;
    insert into public.monitor_records(owner_id,kind,record_key,data)
      values(job.owner_id,'status','cloud:coupons:schedule',jsonb_build_object(
        'coupon_schedule',true,'state',case when failure is null then 'done' else 'failed' end,
        'detail',coalesce(failure,'Busca pública concluída.'),'checked_at',now(),
        'next_at',job.attempted_at+interval '1 hour'))
      on conflict(owner_id,kind,record_key) do update set data=excluded.data,updated_at=now();
    finished := finished+1;
  end loop;
  return finished;
end;
$$;

create function monitor_private.dispatch_coupon_jobs() returns integer
language plpgsql security invoker set search_path = '' as $$
declare
  job record;
  secret text;
  endpoint text;
  request bigint;
  dispatched integer := 0;
begin
  if not pg_try_advisory_xact_lock(hashtext('monitor-precos-coupon-schedule')) then return 0; end if;
  perform monitor_private.finish_coupon_jobs();
  select decrypted_secret into secret from vault.decrypted_secrets where name='monitor_cloud_cron_secret';
  select decrypted_secret into endpoint from vault.decrypted_secrets where name='monitor_cloud_cron_url';
  if secret is null or endpoint is null or endpoint not like '%/api/scheduled/collect' then return 0; end if;
  endpoint := regexp_replace(endpoint,'/api/scheduled/collect$','/api/scheduled/coupons');
  insert into monitor_private.coupon_jobs(owner_id)
    select distinct owner_id from public.monitor_records where kind='components' on conflict do nothing;
  for job in select j.*,coalesce(f.data->>'value','[]')::jsonb as coupons
    from monitor_private.coupon_jobs j left join public.monitor_records f
      on f.owner_id=j.owner_id and f.kind='settings' and f.record_key='cloud_coupon_feed'
    where j.state<>'running' and (j.attempted_at is null or j.attempted_at<now()-interval '1 hour')
      and not exists(select 1 from public.monitor_records s where s.owner_id=j.owner_id
        and s.kind='scans' and s.record_key='coupons' and s.updated_at>now()-interval '5 minutes')
    order by j.attempted_at nulls first limit 2 for update of j skip locked
  loop
    insert into public.monitor_records(owner_id,kind,record_key,data)
      values(job.owner_id,'scans','coupons','{}')
      on conflict(owner_id,kind,record_key) do update set data=excluded.data,updated_at=now()
      where public.monitor_records.updated_at<=now()-interval '5 minutes';
    if not found then continue; end if;
    request := net.http_post(url:=endpoint,body:=jsonb_build_object('coupons',job.coupons),
      headers:=jsonb_build_object('Content-Type','application/json','Authorization','Bearer '||secret),timeout_milliseconds:=45000);
    update monitor_private.coupon_jobs set state='running',attempted_at=now(),request_id=request,
      detail='Busca pública em andamento.' where owner_id=job.owner_id;
    insert into public.monitor_records(owner_id,kind,record_key,data)
      values(job.owner_id,'status','cloud:coupons:schedule',jsonb_build_object(
        'coupon_schedule',true,'state','running','detail','Busca pública em andamento.',
        'checked_at',now(),'next_at',now()+interval '1 hour'))
      on conflict(owner_id,kind,record_key) do update set data=excluded.data,updated_at=now();
    dispatched := dispatched+1;
  end loop;
  return dispatched;
end;
$$;
revoke all on function monitor_private.finish_coupon_jobs(),monitor_private.dispatch_coupon_jobs() from public,anon,authenticated;

-- Habilitar só depois de validar /api/scheduled/coupons no deploy.
-- select cron.schedule('monitor-precos-public-coupons','* * * * *',
--   'select monitor_private.dispatch_coupon_jobs();');
