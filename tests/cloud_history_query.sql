-- Fixtures isoladas; nenhum usuário ou registro de teste permanece.
begin;
insert into auth.users(id) values ('00000000-0000-0000-0000-000000000051'),('00000000-0000-0000-0000-000000000052');
insert into public.monitor_records(owner_id,kind,record_key,data) values
  ('00000000-0000-0000-0000-000000000051','offers','history-fixture','{"id":"history-fixture","component_id":-900000000001}'),
  ('00000000-0000-0000-0000-000000000051','offers','other-piece','{"id":"other-piece","component_id":-900000000002}'),
  ('00000000-0000-0000-0000-000000000052','offers','history-fixture','{"id":"history-fixture","component_id":-900000000001}');
insert into public.monitor_records(owner_id,kind,record_key,data)
  select '00000000-0000-0000-0000-000000000051','observations','history-'||n,
    jsonb_build_object('offer_id','history-fixture','observed_at',now()::text,'pix',100,'case','owned')
  from generate_series(1,10001) n;
insert into public.monitor_records(owner_id,kind,record_key,data) values
  ('00000000-0000-0000-0000-000000000051','observations','history-old',jsonb_build_object('offer_id','history-fixture','observed_at',(now()-interval '40 days')::text,'case','old')),
  ('00000000-0000-0000-0000-000000000051','observations','history-other-piece',jsonb_build_object('offer_id','other-piece','observed_at',now()::text,'case','other')),
  ('00000000-0000-0000-0000-000000000052','observations','history-foreign',jsonb_build_object('offer_id','history-fixture','observed_at',now()::text,'pix',1,'case','foreign'));
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000051',true);
set local role authenticated;
do $$
declare result jsonb;
begin
  result:=public.monitor_recent_observations('-900000000001',current_date-30);
  if jsonb_array_length(result->'rows')<>10000 or result->>'truncated'<>'true' then
    raise exception 'Limite/sinalização de histórico incorretos';
  end if;
  if exists(select 1 from jsonb_array_elements(result->'rows') item where item->>'case'<>'owned') then
    raise exception 'Outra peça, data antiga ou outra conta entrou na consulta';
  end if;
  result:=public.monitor_recent_observations('missing',current_date-30);
  if result->'rows'<>'[]'::jsonb or result->>'truncated'<>'false' then raise exception 'Estado vazio incorreto'; end if;
  if has_function_privilege('anon','public.monitor_recent_observations(text,date)','EXECUTE') then raise exception 'Execução anônima permitida'; end if;
end;
$$;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000052',true);
do $$
declare result jsonb;
begin
  result:=public.monitor_recent_observations('-900000000001',current_date-30);
  if jsonb_array_length(result->'rows')<>1 or result->'rows'->0->>'case'<>'foreign' then
    raise exception 'Consulta não respeitou a segunda conta';
  end if;
end;
$$;
reset role;
rollback;
