-- Aplicar após schema.sql. O Cron só é habilitado depois do deploy e do Vault.
create extension if not exists pg_cron;
create extension if not exists pg_net with schema extensions;
create schema if not exists monitor_private;
revoke all on schema monitor_private from public, anon, authenticated;
-- net/Vault são esquemas internos, fora da Data API; nunca exponha net nela.

create table public.monitor_scheduled_jobs (
  owner_id uuid not null references auth.users(id) on delete cascade,
  component_key text not null,
  shop text not null check (shop in ('Pichau','KaBuM','Amazon','Terabyte Shop')),
  state text not null default 'idle' check (state in ('idle','running','done','failed')),
  attempted_at timestamptz,
  finished_at timestamptz,
  request_id bigint,
  detail text not null default '',
  primary key (owner_id,component_key,shop)
);
alter table public.monitor_scheduled_jobs enable row level security;
create policy monitor_scheduled_jobs_owner on public.monitor_scheduled_jobs
  for select to authenticated using ((select auth.uid()) = owner_id);
revoke all on public.monitor_scheduled_jobs from public, anon, authenticated;
grant select on public.monitor_scheduled_jobs to authenticated;

create function monitor_private.finish_scheduled_jobs() returns integer
language plpgsql security invoker set search_path = '' as $$
declare
  job public.monitor_scheduled_jobs%rowtype;
  response net._http_response%rowtype;
  result jsonb;
  item jsonb;
  component jsonb;
  finished integer := 0;
  failure text;
begin
  for job in select j.* from public.monitor_scheduled_jobs j
    where j.state='running' and (j.attempted_at < now()-interval '4 minutes'
      or exists(select 1 from net._http_response r where r.id=j.request_id))
    for update of j skip locked
  loop
    failure := null;
    result := null;
    select * into response from net._http_response where id=job.request_id;
    if not found or response.timed_out then
      failure := 'Tempo limite da consulta; histórico preservado.';
    elsif response.error_msg is not null or response.status_code is distinct from 200 then
      failure := 'Consulta indisponível (HTTP ' || coalesce(response.status_code::text,'sem resposta') || '); histórico preservado.';
    else
      begin
        result := response.content::jsonb;
        if jsonb_typeof(result->'records') is distinct from 'array'
          or jsonb_array_length(result->'records') > 25
          or result->'status'->>'name' is distinct from job.shop
          or result->'status'->>'component_id' is distinct from job.component_key then
          raise exception 'Resposta de outra consulta ou inválida';
        end if;
        select c.data || coalesce(o.data,'{}') into component
          from public.monitor_records c left join public.monitor_records o
            on o.owner_id=c.owner_id and o.kind='overrides' and o.record_key='component:'||c.record_key
          where c.owner_id=job.owner_id and c.kind='components' and c.record_key=job.component_key;
        if found and coalesce(component->>'enabled','1') in ('1','true')
          and coalesce(component->>'deleted','false') <> 'true' then
          for item in select value from jsonb_array_elements(result->'records') loop
            if jsonb_typeof(item->'data') is distinct from 'object'
              or length(coalesce(item->>'record_key','')) not between 1 and 200
              or coalesce(item->>'kind','') not in ('offers','observations','status') then
              raise exception 'Registro inválido';
            end if;
            if item->>'kind'='offers' then
              if item->'data'->>'component_id' is distinct from job.component_key
                or item->'data'->>'shop' is distinct from job.shop
                or item->>'record_key' is distinct from item->'data'->>'id' then
                raise exception 'Oferta fora da consulta';
              end if;
            elsif item->>'kind'='observations' then
              if not exists(select 1 from public.monitor_records o
                where o.owner_id=job.owner_id and o.kind='offers'
                  and o.record_key=item->'data'->>'offer_id'
                  and o.data->>'component_id'=job.component_key and o.data->>'shop'=job.shop)
                or item->>'record_key' is distinct from (item->'data'->>'offer_id')||':'||(item->'data'->>'observed_at') then
                raise exception 'Histórico fora da consulta';
              end if;
            else
              if item->>'record_key' is distinct from 'cloud:'||job.shop||':'||job.component_key
                or item->'data'->>'component_id' is distinct from job.component_key
                or item->'data'->>'name' is distinct from job.shop then
                raise exception 'Estado fora da consulta';
              end if;
            end if;
            insert into public.monitor_records(owner_id,kind,record_key,data)
              values(job.owner_id,item->>'kind',item->>'record_key',item->'data')
              on conflict(owner_id,kind,record_key) do update set data=excluded.data,updated_at=now()
              where coalesce(public.monitor_records.data->>'checked_at','') <= coalesce(excluded.data->>'checked_at','');
          end loop;
        end if;
        if coalesce((result->'status'->>'count')::integer,0)=0
          and coalesce((result->'status'->>'failures')::integer,0)>0 then
          failure := result->'status'->>'detail';
        end if;
      exception when others then
        failure := 'Resposta inválida; histórico preservado.';
      end;
    end if;
    update public.monitor_scheduled_jobs set state=case when failure is null then 'done' else 'failed' end,
      detail=coalesce(failure,result->'status'->>'detail','Consulta concluída.'),finished_at=now()
      where owner_id=job.owner_id and component_key=job.component_key and shop=job.shop;
    finished := finished+1;
  end loop;
  return finished;
end;
$$;

create function monitor_private.dispatch_scheduled_jobs() returns integer
language plpgsql security invoker set search_path = '' as $$
declare
  job record;
  secret text;
  endpoint text;
  offers jsonb;
  dispatched integer := 0;
  request bigint;
begin
  if not pg_try_advisory_xact_lock(hashtext('monitor-precos-cloud-schedule')) then return 0; end if;
  perform monitor_private.finish_scheduled_jobs();
  select decrypted_secret into secret from vault.decrypted_secrets where name='monitor_cloud_cron_secret';
  select decrypted_secret into endpoint from vault.decrypted_secrets where name='monitor_cloud_cron_url';
  if secret is null or endpoint is null then return 0; end if;
  insert into public.monitor_scheduled_jobs(owner_id,component_key,shop)
    select c.owner_id,c.record_key,s.name from public.monitor_records c
      cross join (values ('Pichau'),('KaBuM'),('Amazon'),('Terabyte Shop')) s(name)
    where c.kind='components' on conflict do nothing;
  for job in
    select j.*,c.data || coalesce(o.data,'{}') as component
      from public.monitor_scheduled_jobs j join public.monitor_records c
        on c.owner_id=j.owner_id and c.kind='components' and c.record_key=j.component_key
      left join public.monitor_records o on o.owner_id=c.owner_id and o.kind='overrides'
        and o.record_key='component:'||c.record_key
      left join public.monitor_records s on s.owner_id=c.owner_id and s.kind='settings' and s.record_key='shop:'||j.shop
      left join public.monitor_records so on so.owner_id=c.owner_id and so.kind='overrides' and so.record_key='shop:'||j.shop
    where j.state<>'running' and (j.attempted_at is null or j.attempted_at < now()-interval '10 minutes')
      and coalesce((c.data || coalesce(o.data,'{}'))->>'enabled','1') in ('1','true')
      and coalesce((c.data || coalesce(o.data,'{}'))->>'deleted','false')<>'true'
      and coalesce(so.data->>'value',s.data->>'value','1')='1'
      and not exists(select 1 from public.monitor_records lock where lock.owner_id=j.owner_id
        and lock.kind='scans' and lock.record_key=j.component_key and lock.updated_at>now()-interval '5 minutes')
    order by j.attempted_at nulls first,j.component_key,j.shop limit 2 for update of j skip locked
  loop
    select coalesce(jsonb_agg(known.data),'[]') into offers from (
      select r.data || coalesce(p.data,'{}') as data from public.monitor_records r
        left join public.monitor_records p on p.owner_id=r.owner_id and p.kind='preferences' and p.record_key=r.record_key
        where r.owner_id=job.owner_id and r.kind='offers' and r.data->>'component_id'=job.component_key
        order by r.updated_at desc limit 500
    ) known;
    request := net.http_post(url:=endpoint,body:=jsonb_build_object('component',job.component,'shop',job.shop,'offers',offers),
      headers:=jsonb_build_object('Content-Type','application/json','Authorization','Bearer '||secret),timeout_milliseconds:=140000);
    update public.monitor_scheduled_jobs set state='running',attempted_at=now(),request_id=request,
      detail='Consulta em andamento.' where owner_id=job.owner_id and component_key=job.component_key and shop=job.shop;
    dispatched := dispatched+1;
  end loop;
  return dispatched;
end;
$$;
revoke all on function monitor_private.finish_scheduled_jobs(), monitor_private.dispatch_scheduled_jobs() from public, anon, authenticated;

-- Vault: monitor_cloud_cron_secret e monitor_cloud_cron_url (endpoint completo).
-- Após validar o deploy: select cron.schedule('monitor-precos-cloud-searches',
--   '* * * * *', 'select monitor_private.dispatch_scheduled_jobs();');
