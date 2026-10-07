-- Integração PostgreSQL. Execute depois de cloud/schema.sql e cloud/schedule.sql.
-- ROLLBACK obrigatório: pg_net só envia requisições depois de COMMIT.
begin;
do $$
declare
  owner uuid := '00000000-0000-0000-0000-000000000051';
  other_owner uuid := '00000000-0000-0000-0000-000000000052';
  fixture jsonb := '{"id":-900000000001,"name":"Teste isolado","kind":"custom","query":"rtx 5060","enabled":1}';
  reading jsonb;
  status jsonb;
  result jsonb;
  record jsonb;
  number integer;
begin
  insert into auth.users(id) values(owner),(other_owner);
  insert into public.monitor_records(owner_id,kind,record_key,data)
    values(owner,'components','-900000000001',fixture),
      (other_owner,'components','-900000000001',fixture),
      (owner,'offers','fixture-one','{"id":"fixture-one","component_id":-900000000001,"shop":"Pichau","pix":100,"checked_at":"2030-01-02T00:00:00Z"}');
  insert into public.monitor_scheduled_jobs(owner_id,component_key,shop,state,attempted_at,request_id)
    values(owner,'-900000000001','Pichau','running',now(),-900001),
      (owner,'-900000000001','Amazon','running',now()-interval '5 minutes',-900002),
      (owner,'-900000000001','KaBuM','running',now(),-900003),
      (other_owner,'-900000000001','Pichau','idle',null,null);
  reading := jsonb_build_object('id','fixture-one','component_id',-900000000001,'shop','Pichau',
    'pix',200,'url','https://www.pichau.com.br/fixture','checked_at','2030-01-01T00:00:00Z');
  status := jsonb_build_object('name','Pichau','component_id',-900000000001,'count',1,'failures',0,'detail','Teste');
  result := jsonb_build_object('status',status,'records',jsonb_build_array(
    jsonb_build_object('kind','offers','record_key','fixture-one','data',reading),
    jsonb_build_object('kind','observations','record_key','fixture-one:2030-01-01T00:00:00Z',
      'data',jsonb_build_object('offer_id','fixture-one','observed_at','2030-01-01T00:00:00Z','pix',200)),
    jsonb_build_object('kind','status','record_key','cloud:Pichau:-900000000001','data',status)));
  insert into net._http_response(id,status_code,content) values(-900001,200,result::text);
  -- Um registro válido seguido de outro inválido não pode persistir parcialmente.
  reading := jsonb_build_object('id','fixture-invalid','component_id',-900000000001,'shop','KaBuM');
  record := jsonb_build_object('kind','offers','record_key','fixture-invalid','data',reading);
  result := jsonb_build_object('status',jsonb_build_object('name','KaBuM','component_id',-900000000001),
    'records',jsonb_build_array(record,jsonb_build_object('kind','settings','record_key','arbitrary','data','{}'::jsonb)));
  insert into net._http_response(id,status_code,content) values(-900003,200,result::text);
  number := monitor_private.finish_scheduled_jobs();
  if number<>3 then raise exception 'Resultados não consumidos'; end if;
  if (select data->>'pix' from public.monitor_records where owner_id=owner and kind='offers' and record_key='fixture-one')<>'100' then
    raise exception 'Consulta antiga sobrescreveu preço recente'; end if;
  if not exists(select 1 from public.monitor_records where owner_id=owner and kind='observations' and record_key='fixture-one:2030-01-01T00:00:00Z') then
    raise exception 'Histórico não persistido'; end if;
  if exists(select 1 from public.monitor_records where kind='offers' and record_key='fixture-invalid') then
    raise exception 'Resposta inválida parcialmente persistida'; end if;
  if (select count(*) from public.monitor_scheduled_jobs where owner_id=owner and state='failed')<>2 then
    raise exception 'Timeout/resposta inválida não encerrados'; end if;
  if monitor_private.finish_scheduled_jobs()<>0 then raise exception 'Resposta reaplicada'; end if;

  -- Configuração só existe nesta transação. Nenhuma requisição será enviada.
  if not exists(select 1 from vault.secrets where name='monitor_cloud_cron_secret') then
    perform vault.create_secret('test-only-not-a-credential','monitor_cloud_cron_secret');
  end if;
  if not exists(select 1 from vault.secrets where name='monitor_cloud_cron_url') then
    perform vault.create_secret('https://example.invalid/api/scheduled/collect','monitor_cloud_cron_url');
  end if;
  -- Pausar os dados existentes temporariamente para selecionar somente fixtures.
  update public.monitor_records set data=data || '{"enabled":0}' where kind='components';
  update public.monitor_records set data=fixture where owner_id=owner and kind='components' and record_key='-900000000001';
  insert into public.monitor_records(owner_id,kind,record_key,data) values
    (owner,'overrides','shop:Amazon','{"value":"0"}');
  update public.monitor_scheduled_jobs set attempted_at=null,state='idle' where owner_id=owner;
  number := monitor_private.dispatch_scheduled_jobs();
  if number<>2 then raise exception 'Limite de dois lotes não respeitado'; end if;
  if exists(select 1 from public.monitor_scheduled_jobs where owner_id=owner and shop='Amazon' and state='running') then
    raise exception 'Fonte pausada consultada'; end if;
  if monitor_private.dispatch_scheduled_jobs()<>1 then raise exception 'Lote duplicado ou rodada restante perdida'; end if;
  if monitor_private.dispatch_scheduled_jobs()<>0 then raise exception 'Intervalo mínimo não respeitado'; end if;
  update public.monitor_scheduled_jobs set state='idle',attempted_at=now()-interval '11 minutes' where owner_id=owner;
  insert into public.monitor_records(owner_id,kind,record_key,data) values(owner,'scans','-900000000001','{}');
  if monitor_private.dispatch_scheduled_jobs()<>0 then raise exception 'Consulta manual em andamento ignorada'; end if;
  delete from public.monitor_records where owner_id=owner and kind='scans';
  update public.monitor_records set data=data || '{"enabled":0}' where owner_id=owner and kind='components';
  if monitor_private.dispatch_scheduled_jobs()<>0 then raise exception 'Peça pausada consultada'; end if;
  update public.monitor_records set data=fixture where owner_id=owner and kind='components';
  insert into public.monitor_records(owner_id,kind,record_key,data) values(owner,'overrides','component:-900000000001','{"deleted":true}');
  if monitor_private.dispatch_scheduled_jobs()<>0 then raise exception 'Peça excluída consultada'; end if;
end;
$$;
set local role authenticated;
select set_config('request.jwt.claims','{"sub":"00000000-0000-0000-0000-000000000051","role":"authenticated"}',true);
do $$
begin
  if (select count(*) from public.monitor_scheduled_jobs where component_key='-900000000001')<>4 then
    raise exception 'Isolamento por conta incorreto'; end if;
  begin
    perform monitor_private.dispatch_scheduled_jobs();
    raise exception 'Usuário pode disparar Cron interno';
  exception when insufficient_privilege then null;
  end;
  begin
    update public.monitor_scheduled_jobs set detail='alterado';
    raise exception 'Usuário pode alterar a fila agendada';
  exception when insufficient_privilege then null;
  end;
end;
$$;
reset role;
rollback;
select 'Persistência, timeout, atomicidade, isolamento, pausas e intervalo validados; fixtures revertidas.' as validation;
