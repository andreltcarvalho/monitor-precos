-- Nenhuma requisição sai: pg_net só envia depois de COMMIT e a fixture usa ROLLBACK.
begin;
insert into auth.users(id) values('00000000-0000-0000-0000-000000000061'),('00000000-0000-0000-0000-000000000062');
set local role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000061',true);
select set_config('request.jwt.claims','{"sub":"00000000-0000-0000-0000-000000000061","role":"authenticated"}',true);
do $$
declare config jsonb;
begin
  perform public.monitor_telegram_save('123456789:synthetic_fixture_synthetic_fixture_','fixture_bot');
  config:=public.monitor_telegram_config();
  if config->>'token'<>'123456789:synthetic_fixture_synthetic_fixture_' then raise exception 'Segredo próprio não salvo'; end if;
  perform public.monitor_telegram_recipient(config->>'nonce','123456');
  if public.monitor_telegram_config()->>'chat_id'<>'123456' then raise exception 'Destinatário não salvo'; end if;
  begin
    perform 1 from monitor_private.telegram_connections;
    raise exception 'Tabela privada acessível';
  exception when insufficient_privilege then null; end;
  if has_function_privilege('anon','public.monitor_telegram_config()','execute') then raise exception 'RPC anônimo permitido'; end if;
  if has_function_privilege('authenticated',(select p.oid from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='monitor_private' and p.proname='dispatch_telegram_notifications'),'execute') then raise exception 'Agendador público'; end if;
end;
$$;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000062',true);
select set_config('request.jwt.claims','{"sub":"00000000-0000-0000-0000-000000000062","role":"authenticated"}',true);
do $$ begin if public.monitor_telegram_config()<>'{}'::jsonb then raise exception 'Segredo de outra conta vazou'; end if; end; $$;
reset role;
-- Isolar outras contas nesta transação, preservadas pelo rollback.
update monitor_private.telegram_connections set enabled=false,evaluation_id=null where owner_id<>'00000000-0000-0000-0000-000000000061';
do $$
declare owner uuid:='00000000-0000-0000-0000-000000000061'; part jsonb; offer jsonb; candidate jsonb;
  revision uuid; request bigint; count integer;
begin
  part:='{"id":-900000000061,"name":"Fixture","kind":"custom","query":"rtx 5060","enabled":1,"notification_target":1000}';
  offer:=jsonb_build_object('id','notify-fixture','component_id',-900000000061,'shop','Pichau',
    'checked_at',now(),'valid_until',now()+interval '10 minutes','pix',900,'title','RTX 5060',
    'url','https://www.pichau.com.br/fixture','availability','in');
  insert into public.monitor_records(owner_id,kind,record_key,data) values
    (owner,'components','-900000000061',part),(owner,'offers','notify-fixture',offer);
  candidate:=jsonb_build_object('identity',repeat('a',64),'price',900,'offer_id','notify-fixture',
    'component_key','-900000000061','threshold',1000,'checked_at',offer->'checked_at',
    'valid_until',offer->'valid_until','text','Teste sintético não enviado','component',part,'reading',offer);
  update monitor_private.telegram_connections set evaluation_id=-900061,evaluated_at=now() where owner_id=owner;
  insert into net._http_response(id,status_code,content) values(-900061,200,jsonb_build_object('notifications',jsonb_build_array(candidate))::text);
  count:=monitor_private.dispatch_telegram_notifications();
  if count<>1 then raise exception 'Aviso elegível não enfileirado'; end if;
  select request_id,telegram_deliveries.revision into request,revision from monitor_private.telegram_deliveries where owner_id=owner and identity=repeat('a',64);
  if monitor_private.dispatch_telegram_notifications()<>0 then raise exception 'Envio duplicado em andamento'; end if;
  insert into net._http_response(id,status_code,content) values(request,200,'{"ok":true,"result":{"message_id":1}}');
  perform monitor_private.dispatch_telegram_notifications();
  if (select state from monitor_private.telegram_deliveries where owner_id=owner and identity=repeat('a',64))<>'sent' then raise exception 'Sucesso não registrado'; end if;
  insert into monitor_private.telegram_deliveries(owner_id,identity,price,payload,revision)
    values(owner,repeat('a',64),950,candidate||'{"price":950}',revision),
      (owner,repeat('b',64),900,candidate||jsonb_build_object('identity',repeat('b',64),'threshold',1200),revision);
  if monitor_private.dispatch_telegram_notifications()<>0 then raise exception 'Aviso antigo ou preço pior enviado'; end if;
  if exists(select 1 from monitor_private.telegram_deliveries where owner_id=owner and state='pending') then raise exception 'Limites alterados não cancelaram pendências'; end if;
  insert into monitor_private.telegram_deliveries(owner_id,identity,price,payload,revision,state,request_id,attempted_at,attempts)
    values(owner,repeat('c',64),900,candidate,revision,'sending',-900062,now(),1),
      (owner,repeat('d',64),900,candidate,revision,'sending',-900063,now()-interval '4 minutes',1);
  insert into net._http_response(id,status_code,content) values(-900062,429,'{"ok":false,"error_code":429,"parameters":{"retry_after":600}}');
  perform monitor_private.dispatch_telegram_notifications();
  if (select state from monitor_private.telegram_deliveries where owner_id=owner and identity=repeat('c',64))<>'failed' then raise exception '429 não registrado'; end if;
  if (select retry_at from monitor_private.telegram_deliveries where owner_id=owner and identity=repeat('c',64))<now()+interval '9 minutes' then raise exception 'Pausa do Telegram ignorada'; end if;
  if (select state from monitor_private.telegram_deliveries where owner_id=owner and identity=repeat('d',64))<>'uncertain' then raise exception 'Timeout reenviado às cegas'; end if;
  insert into monitor_private.telegram_deliveries(owner_id,identity,price,payload,revision,state,request_id,attempted_at,attempts)
    values(owner,repeat('e',64),900,candidate,revision,'sending',-900064,now(),1);
  insert into net._http_response(id,status_code,content) values(-900064,403,'{"ok":false,"error_code":403}');
  perform monitor_private.dispatch_telegram_notifications();
  if (select enabled from monitor_private.telegram_connections where owner_id=owner) then raise exception 'Bot bloqueado não pausado'; end if;
end;
$$;
rollback;
select 'Alertas: isolamento, Vault, limite, deduplicação, confirmação, 429, timeout e bloqueio aprovados; nenhuma mensagem enviada.' as validation;
