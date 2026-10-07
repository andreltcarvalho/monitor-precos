# Agendamento HTTP pelo Supabase

Escopo autorizado: Supabase Cron aciona a coleta Python na Vercel, sem Vercel Cron/Workflow. Mercado Livre, Shopee, OLX e Telegram continuam no PC.

- Extrair a coleta por peça/loja de `cloud/app.py` para reutilização na consulta manual e no endpoint interno agendado.
- Endpoint autenticado por segredo aleatório exclusivo, configurado no ambiente Vercel e no Vault Supabase. Recebe somente o lote da peça/loja; devolve leituras, sem acesso administrativo ao banco.
- Supabase `pg_cron` + `pg_net`: distribuir no máximo duas consultas por minuto, intervalo de dez minutos por peça/loja, fontes/peças pausadas respeitadas. Uma função interna persiste as respostas e recupera timeouts; o histórico permanece sob RLS por conta.
- Validar autenticação, corte/ocultas, mesma coleta manual/agendada, SQL de persistência/concorrência/pausas, regressões existentes e ciclo real Cron → Vercel → Supabase. Publicar código sem segredos.

Concluído: endpoint e SQL publicados, Vault/ambientes configurados, job ativo e ciclo real com ofertas/histórico persistidos. 494 testes Python e integração SQL transacional aprovados. Bloqueios de lojas continuam sendo falhas de leitura, sem apagar histórico ou produzir sucesso fictício.
