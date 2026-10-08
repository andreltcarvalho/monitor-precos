-- Uma preferência muda sem apagar outros campos ou gravações concorrentes.
create function public.monitor_set_preference(offer_key text,preference_field text,enabled boolean) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare result jsonb;
begin
  if preference_field not in ('favorite','hidden') or preference_field is null or enabled is null then
    raise exception 'Preferência inválida' using errcode='22023';
  end if;
  if not exists(select 1 from public.monitor_records where owner_id=(select auth.uid())
      and kind='offers' and record_key=offer_key) then return null; end if;
  insert into public.monitor_records(owner_id,kind,record_key,data)
    values((select auth.uid()),'preferences',offer_key,jsonb_build_object(preference_field,enabled))
    on conflict(owner_id,kind,record_key) do update
      set data=public.monitor_records.data||excluded.data,updated_at=now()
    returning data into result;
  return result;
end;
$$;
revoke execute on function public.monitor_set_preference(text,text,boolean) from public,anon;
grant execute on function public.monitor_set_preference(text,text,boolean) to authenticated;
