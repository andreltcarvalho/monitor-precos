-- Histórico restrito à conta, peça e período. RLS continua ativo.
create function public.monitor_recent_observations(component_key text, since_day date) returns jsonb
language sql stable security invoker set search_path = '' as $$
  with recent as (
    select observation.data,
      row_number() over (order by observation.data->>'observed_at' desc, observation.record_key) as ordinal
    from public.monitor_records observation
    join public.monitor_records offer on offer.owner_id=observation.owner_id
      and offer.kind='offers' and offer.record_key=observation.data->>'offer_id'
    where observation.owner_id=(select auth.uid()) and observation.kind='observations'
      and offer.data->>'component_id'=component_key
      and left(observation.data->>'observed_at',10) >= greatest(since_day,current_date-31)::text
    order by observation.data->>'observed_at' desc, observation.record_key
    limit 10001
  )
  select jsonb_build_object(
    'rows',coalesce(jsonb_agg(data order by ordinal) filter (where ordinal<=10000),'[]'::jsonb),
    'truncated',count(*)>10000) from recent;
$$;
revoke execute on function public.monitor_recent_observations(text,date) from public,anon;
grant execute on function public.monitor_recent_observations(text,date) to authenticated;
