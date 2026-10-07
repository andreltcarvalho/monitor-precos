# Vercel + Supabase

Status: implementação, testes, RLS e produção concluídos. Painel: https://monitor-precos-snowy.vercel.app. Conexão autenticada do PC depende da conta confirmada do usuário e de `Conectar-Nuvem.cmd`; agendamento cloud adiado.

Escopo autorizado em 07/10/2026: painel web separado, preservando o aplicativo local; Mercado Livre, OLX, Shopee, Telegram e aplicação de cupons continuam no PC. Pichau, KaBuM, Amazon, Terabyte e cupons públicos podem ser consultados por requisição na Vercel. Agendamento externo fica para depois.

## Implementação

- `cloud/`: FastAPI, sessão Supabase Auth, API por requisição, catálogo web com as regras atuais, peças, fontes, cupons, usados e histórico. Reutilizar parsers e regras do projeto; nenhum Chrome ou loop contínuo no servidor.
- Supabase: registros e comandos persistidos por conta, com RLS em todas as tabelas. Apenas chave publicável e tokens do usuário; nenhuma chave administrativa no navegador ou no coletor local.
- `cloud_sync.py` e `configure_cloud.py`: conexão local autenticada, token de renovação protegido por DPAPI, envio incremental de dados e execução de comandos pelo monitor existente. Não enviar arquivos, cookies, sessões ou credenciais de lojas/Telegram.
- Vercel: entrypoint explícito para a versão cloud, dependências e arquivos privados excluídos, variáveis por ambiente; primeiro preview, depois produção.

## Validação

Regressões de autenticação, isolamento entre contas, preços/limites, comandos locais e exportação de dados permitidos. Testar RLS no projeto real, API/UI em processo isolado, build/deploy e endpoints reais. Distinguir simulações de login/sincronização autenticados reais. Não reiniciar nem migrar o banco local para testar.
