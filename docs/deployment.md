# Hospedar sua instância

[Documentação](README.md) · [Arquitetura](architecture.md)

O painel e as consultas HTTP rodam na Vercel; conta, histórico e agendamento ficam no Supabase. Chrome, grupos do Telegram e ativação de cupons do Mercado Livre continuam no PC.

## 1. Preparar o Supabase

Crie um projeto e aplique os arquivos nesta ordem, em uma instalação nova:

| Ordem | SQL | Responsabilidade |
| --- | --- | --- |
| 1 | [schema.sql](../cloud/schema.sql) | Registros por conta, fila de comandos, RLS e RPCs do painel. |
| 2 | [schedule.sql](../cloud/schedule.sql) | Cron, pg_net e fila de consultas HTTP. |
| 3 | [coupon_schedule.sql](../cloud/coupon_schedule.sql) | Coleta automática de cupons públicos. |
| 4 | [notifications.sql](../cloud/notifications.sql) | Bot, histórico privado de entregas e agendamento de avisos. |

Use o SQL Editor ou seu fluxo de migrations para aplicar os arquivos. Não rode novamente `schema.sql` numa base existente: ele contém criação de tabelas e funções. Não é necessário importar seu banco local para instalar o painel.

Configure o endereço público do seu painel nas opções de autenticação e confirmação de e-mail do projeto. Os usuários criam suas próprias contas pelo app. Mantenha `monitor_private`, `vault` e `net` fora dos schemas expostos na Data API.

## 2. Preparar a Vercel

Importe o repositório do GitHub. O projeto já declara o framework FastAPI e o entrypoint `cloud.app:app` em [vercel.json](../vercel.json) e [pyproject.toml](../pyproject.toml); não precisa de build React ou de um servidor Python contínuo.

Configure estas variáveis no ambiente de produção:

| Variável | Valor |
| --- | --- |
| `SUPABASE_URL` | URL do seu projeto Supabase. |
| `SUPABASE_PUBLISHABLE_KEY` | Chave publicável do projeto; a API também exige JWT do usuário. |
| `MONITOR_PUBLIC_URL` | URL HTTPS do painel, sem barra final. |
| `MONITOR_CRON_SECRET` | Segredo aleatório exclusivo para os endpoints agendados. |

Para gerar o segredo no seu terminal:

```powershell
py -3.12 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Guarde-o nas configurações da hospedagem e no Vault. Não o inclua no Git. As variáveis de Preview são configuradas separadamente se você quiser testar esses deploys; o agendamento deve apontar para produção.

Publique e confira `/health`: deve responder 200, com `configured: true`. A interface abre a tela de login; `/api/catalog` sem sessão deve responder 401.

## 3. Configurar o agendamento

No Vault do Supabase, crie estes dois segredos:

| Nome | Conteúdo |
| --- | --- |
| `monitor_cloud_cron_secret` | O mesmo valor de `MONITOR_CRON_SECRET` na Vercel. |
| `monitor_cloud_cron_url` | URL completa de produção terminando em `/api/scheduled/collect`. |

Os agendamentos de cupons e alertas derivam seus endpoints dessa URL e reutilizam o segredo. Se os registros já existem, atualize-os em vez de criar duplicatas.

Depois de validar o deploy e os segredos, habilite os jobs no Supabase:

```sql
select cron.schedule('monitor-precos-cloud-searches', '* * * * *',
  'select monitor_private.dispatch_scheduled_jobs();');
select cron.schedule('monitor-precos-public-coupons', '* * * * *',
  'select monitor_private.dispatch_coupon_jobs();');
select cron.schedule('monitor-precos-telegram-alerts', '* * * * *',
  'select monitor_private.dispatch_telegram_notifications();');
```

A frequência do job não é a frequência de consulta de cada loja. Os limites de peça/loja, cupons e mensagens estão em [Arquitetura → Agendamentos](architecture.md#agendamentos).

Confira as execuções em `cron.job_run_details` e as consultas em `public.monitor_scheduled_jobs`. Erro ou timeout preserva os dados anteriores. Não é usado Vercel Cron.

## 4. Conectar o PC e o bot

Execute `Conectar-Nuvem.cmd`, informe a URL da sua instância e entre na mesma conta usada no painel. [Siga a instalação do coletor](getting-started.md#conectar-sua-conta) e conecte as sessões das lojas em Fontes.

O redirecionamento em `app.py` aponta para o painel de referência do projeto. Em uma instância própria, abra sua URL diretamente no navegador; o endereço configurado em `Conectar-Nuvem.cmd` controla a sincronização.

O bot não é criado pelo deploy. Cada usuário deve [conectar seu bot de alertas](integrations.md#bot-de-alertas) e enviar um teste pelo painel.

## Atualizar uma instalação existente

Publique o código pelo repositório e aplique somente o SQL que ainda não foi instalado. Os arquivos abaixo são atualizações para bases antigas; suas definições já estão incluídas em `schema.sql` para instalações novas:

- [history_query.sql](../cloud/history_query.sql): consulta do histórico por conta/peça/período.
- [preferences_query.sql](../cloud/preferences_query.sql): gravação atômica de favorita/ocultação.
- [session_commands.sql](../cloud/session_commands.sql): comandos de abertura e confirmação de sessão.

Mudanças no coletor exigem atualização do checkout e reinício do processo local. Mudanças só na documentação não exigem reinício nem alteração de banco.
