-- Sem chamadas externas: pg_net só envia depois de COMMIT. Reverter todas as fixtures.
begin;
insert into auth.users(id) values('00000000-0000-0000-0000-000000000051'),('00000000-0000-0000-0000-000000000052');
update monitor_private.coupon_jobs set state='done',attempted_at=now();
insert into monitor_private.coupon_jobs(owner_id,state,attempted_at)
  select distinct owner_id,'done',now() from public.monitor_records where kind='components' on conflict do nothing;
insert into public.monitor_records(owner_id,kind,record_key,data) values
  ('00000000-0000-0000-0000-000000000051','components','coupon-fixture','{"id":-900000000001,"enabled":true}'),
  ('00000000-0000-0000-0000-000000000052','components','coupon-fixture','{"id":-900000000001,"enabled":true}');
do $$
declare
  owner uuid := '00000000-0000-0000-0000-000000000051';
  other_owner uuid := '00000000-0000-0000-0000-000000000052';
  statuses jsonb;
  result jsonb;
begin
  if has_function_privilege('anon','monitor_private.dispatch_coupon_jobs()','EXECUTE')
    or has_function_privilege('authenticated','monitor_private.finish_coupon_jobs()','EXECUTE') then
    raise exception 'Função privada exposta'; end if;
  statuses := (select jsonb_agg(jsonb_build_object('source',name,'coupon_source',true,'failures',0,'checked_at',now()))
    from (values('Pichau'),('Melhores Cartões'),('Pelando')) s(name));
  result := jsonb_build_object('status',statuses,'coupons',jsonb_build_array(
    jsonb_build_object('source','Pelando','code','FIXTURE','found_at',now())));
  insert into monitor_private.coupon_jobs(owner_id,state,attempted_at,request_id)
    values(owner,'running',now(),-910001),(other_owner,'running',now()-interval '3 minutes',-910002);
  insert into net._http_response(id,status_code,content) values(-910001,200,result::text);
  perform monitor_private.finish_coupon_jobs();
  if (select state from monitor_private.coupon_jobs where owner_id=owner)<>'done'
    or (select state from monitor_private.coupon_jobs where owner_id=other_owner)<>'failed' then
    raise exception 'Resultado/timeout não encerrados'; end if;
  if (select ((data->>'value')::jsonb)->0->>'code' from public.monitor_records
      where owner_id=owner and kind='settings' and record_key='cloud_coupon_feed')<>'FIXTURE'
    or exists(select 1 from public.monitor_records where owner_id=other_owner and kind='settings' and record_key='cloud_coupon_feed') then
    raise exception 'Cache não salvo ou vazou entre contas'; end if;
  if monitor_private.finish_coupon_jobs()<>0 then raise exception 'Reaplicação'; end if;
  -- A atualização manual posterior à chamada tem prioridade.
  update monitor_private.coupon_jobs set state='running',attempted_at=now()-interval '1 minute' where owner_id=owner;
  update public.monitor_records set data='{"value":"[{\"code\":\"MANUAL\"}]"}',updated_at=now()
    where owner_id=owner and kind='settings' and record_key='cloud_coupon_feed';
  perform monitor_private.finish_coupon_jobs();
  if (select ((data->>'value')::jsonb)->0->>'code' from public.monitor_records
    where owner_id=owner and kind='settings' and record_key='cloud_coupon_feed')<>'MANUAL' then
    raise exception 'Resposta antiga sobrescreveu consulta manual'; end if;
  -- Resposta incompleta não pode gravar parte dos estados.
  update monitor_private.coupon_jobs set state='running',attempted_at=now()-interval '1 minute',request_id=-910003 where owner_id=owner;
  insert into net._http_response(id,status_code,content) values(-910003,200,'{"coupons":[],"status":[]}');
  perform monitor_private.finish_coupon_jobs();
  if (select state from monitor_private.coupon_jobs where owner_id=owner)<>'failed' then raise exception 'Resposta inválida aceita'; end if;
  -- Horário e cooldown do botão impedem novo lote e chamadas duplicadas.
  update monitor_private.coupon_jobs set attempted_at=now(),state='done';
  if monitor_private.dispatch_coupon_jobs()<>0 then raise exception 'Intervalo de uma hora ignorado'; end if;
  update monitor_private.coupon_jobs set attempted_at=now()-interval '2 hours' where owner_id=owner;
  insert into public.monitor_records(owner_id,kind,record_key,data) values(owner,'scans','coupons','{}');
  if monitor_private.dispatch_coupon_jobs()<>0 then raise exception 'Cooldown manual ignorado'; end if;
  delete from public.monitor_records where owner_id=owner and kind='scans' and record_key='coupons';
  if monitor_private.dispatch_coupon_jobs()<>1 then raise exception 'Lote não iniciado'; end if;
  if monitor_private.dispatch_coupon_jobs()<>0 then raise exception 'Lote duplicado'; end if;
end;
$$;
rollback;
select 'Cupons: cache, contas, timeout, atualização manual, intervalo e cooldown validados; fixtures revertidas.' as validation;
