create table public.monitor_records (
  owner_id uuid not null references auth.users(id) on delete cascade,
  kind text not null check (kind in ('components','offers','observations','sources','settings','coupons','coupon_applications','olx_searches','olx_listings','olx_observations','status','preferences','overrides','scans')),
  record_key text not null check (length(record_key) between 1 and 200),
  data jsonb not null check (jsonb_typeof(data) = 'object'),
  updated_at timestamptz not null default now(),
  primary key (owner_id,kind,record_key)
);
create index monitor_records_updated on public.monitor_records(owner_id,kind,updated_at desc);
alter table public.monitor_records enable row level security;
create policy monitor_records_owner on public.monitor_records to authenticated
  using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id);
grant select,insert,update,delete on public.monitor_records to authenticated;
revoke all on public.monitor_records from anon;

create table public.monitor_commands (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  action text not null check (action in ('scan','check','coupon_batch','coupon_retry','coupon_disabled','component_delete','source_save','source_toggle','source_delete','olx_save','olx_toggle','olx_delete','olx_scan','session_open','session_confirm')),
  payload jsonb not null default '{}',
  status text not null default 'pending' check (status in ('pending','running','done','failed')),
  detail text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index monitor_commands_pending on public.monitor_commands(owner_id,status,created_at);
alter table public.monitor_commands enable row level security;
create policy monitor_commands_owner on public.monitor_commands to authenticated
  using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id);
grant select,insert,update,delete on public.monitor_commands to authenticated;
revoke all on public.monitor_commands from anon;

create function public.monitor_claim_commands() returns setof public.monitor_commands
language sql security invoker set search_path = '' as $$
  update public.monitor_commands set status='running',updated_at=now()
  where id in (select id from public.monitor_commands
    where owner_id=(select auth.uid()) and status='pending'
    order by created_at for update skip locked limit 5)
  returning *;
$$;
revoke execute on function public.monitor_claim_commands() from public,anon;
grant execute on function public.monitor_claim_commands() to authenticated;

create function public.monitor_claim_scan(component_key text) returns boolean
language plpgsql security invoker set search_path = '' as $$
declare claimed boolean;
begin
  insert into public.monitor_records(owner_id,kind,record_key,data)
  values ((select auth.uid()),'scans',component_key,jsonb_build_object('started_at',now()))
  on conflict(owner_id,kind,record_key) do update
    set data=excluded.data,updated_at=now()
    where public.monitor_records.updated_at < now()-interval '5 minutes';
  claimed := found;
  return claimed;
end;
$$;
revoke execute on function public.monitor_claim_scan(text) from public,anon;
grant execute on function public.monitor_claim_scan(text) to authenticated;
