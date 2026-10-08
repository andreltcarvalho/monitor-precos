-- Recupera controles de login no painel único. Não altera RLS, dados ou permissões.
alter table public.monitor_commands drop constraint monitor_commands_action_check;
alter table public.monitor_commands add constraint monitor_commands_action_check check
  (action in ('scan','check','coupon_batch','coupon_retry','coupon_disabled','component_delete',
   'source_save','source_toggle','source_delete','olx_save','olx_toggle','olx_delete','olx_scan',
   'session_open','session_confirm'));
