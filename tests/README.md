# Testes

[Comandos de execução](../docs/development.md#testes-de-regressão)

## Python

`python -m unittest discover -s tests -v` reúne regressões de identificação de peças, preços, agrupamento, limites, parsers de lojas, sessões, cupons, OLX, API e sincronização.

- [test_cloud.py](test_cloud.py): catálogo, API, autorização e ponte local/cloud.
- [test_cloud_schedule.py](test_cloud_schedule.py): contrato de consultas agendadas e cupons públicos.
- [test_notifications.py](test_notifications.py): limite do alerta, deduplicação, pareamento e tratamento de falhas do bot.
- Os demais `test_*.py` cobrem regras e integrações locais com fixtures.

## JavaScript

Os arquivos `test_cloud_*_ui.js` executam a interface com DOM/fetch controlados em Node.js: catálogo e pagamentos, autenticação, favoritas, histórico e atualização individual. Não abrem navegador nem acessam a conta real.

## Chrome

- [verify_cloud_ui.py](verify_cloud_ui.py): navegação, filtros, estados, foco e fila de pedidos.
- [verify_notifications_ui.py](verify_notifications_ui.py): campo de valor, pareamento, teste e pausa dos avisos.

Usam Chrome real com API ASGI, repositório em memória e serviços simulados. Capturas são locais em `tmp/`; mensagens, ofertas e comandos não vão para produção.

## PostgreSQL

| Teste | Pré-requisitos além de schema.sql |
| --- | --- |
| [cloud_schedule.sql](cloud_schedule.sql) | `cloud/schedule.sql` |
| [cloud_coupon_schedule.sql](cloud_coupon_schedule.sql) | `cloud/schedule.sql` e `cloud/coupon_schedule.sql` |
| [cloud_notifications.sql](cloud_notifications.sql) | `cloud/schedule.sql` e `cloud/notifications.sql` |
| [cloud_history_query.sql](cloud_history_query.sql) | Consulta de histórico do schema atual. |
| [cloud_preferences_query.sql](cloud_preferences_query.sql) | RPC de preferências do schema atual. |

Executar em projeto de teste; manter o `ROLLBACK` do arquivo. Fixtures não devem permanecer no banco. pg_net só envia depois do commit, portanto os testes transacionais não enviam as requisições enfileiradas.

## Limites da validação

Regressões controladas protegem o comportamento do código. Consultas reais, login/CAPTCHA e envio a um bot conectado são verificações separadas. Não trate uma página bloqueada como resultado vazio nem um teste simulado como prova de acesso real à loja.
