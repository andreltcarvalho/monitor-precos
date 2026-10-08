-- A gravação parcial respeita RLS e não altera outra conta. Todas as fixtures são revertidas.
begin;
insert into auth.users(id) values('00000000-0000-0000-0000-000000000051'),('00000000-0000-0000-0000-000000000052');
insert into public.monitor_records(owner_id,kind,record_key,data) values
  ('00000000-0000-0000-0000-000000000051','offers','preference-fixture','{"id":"preference-fixture"}'),
  ('00000000-0000-0000-0000-000000000052','offers','preference-fixture','{"id":"preference-fixture"}'),
  ('00000000-0000-0000-0000-000000000052','offers','foreign-only','{"id":"foreign-only"}');
set local role authenticated;
select set_config('request.jwt.claims','{"sub":"00000000-0000-0000-0000-000000000051","role":"authenticated"}',true);
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000051',true);
do $$
declare result jsonb;
begin
  if public.monitor_set_preference('preference-fixture','favorite',true)<>'{"favorite":true}'::jsonb then raise exception 'Primeiro campo não salvo'; end if;
  if public.monitor_set_preference('preference-fixture','hidden',true)<>'{"favorite":true,"hidden":true}'::jsonb then raise exception 'Outro campo apagado'; end if;
  if public.monitor_set_preference('preference-fixture','favorite',false)<>'{"favorite":false,"hidden":true}'::jsonb then raise exception 'Alteração apagou outro estado'; end if;
  if public.monitor_set_preference('foreign-only','favorite',true) is not null then raise exception 'Oferta de outra conta alterada'; end if;
  if public.monitor_set_preference('missing','favorite',true) is not null then raise exception 'Oferta ausente aceita'; end if;
  begin
    perform public.monitor_set_preference('preference-fixture','arbitrary',true);
    raise exception 'Campo arbitrário aceito';
  exception when invalid_parameter_value then null;
  end;
  if has_function_privilege('anon','public.monitor_set_preference(text,text,boolean)','EXECUTE') then raise exception 'Acesso anônimo permitido'; end if;
end;
$$;
select set_config('request.jwt.claims','{"sub":"00000000-0000-0000-0000-000000000052","role":"authenticated"}',true);
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000052',true);
do $$
begin
  if public.monitor_set_preference('preference-fixture','favorite',true)<>'{"favorite":true}'::jsonb then raise exception 'Estado da primeira conta vazou'; end if;
end;
$$;
reset role;
do $$
begin
  if (select data from public.monitor_records where owner_id='00000000-0000-0000-0000-000000000051' and kind='preferences' and record_key='preference-fixture')<>'{"favorite":false,"hidden":true}'::jsonb then raise exception 'Outra conta foi alterada'; end if;
end;
$$;
rollback;
select 'Preferências: preservação de campos, propriedade, RLS e validação aprovados; fixtures revertidas.' as validation;
