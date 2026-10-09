# Desenvolvimento

[Documentação](README.md) · [Arquitetura](architecture.md) · [Mapa dos testes](../tests/README.md)

Execute os comandos a partir da raiz do repositório. Use Python 3.12; Node.js é necessário apenas para os testes JavaScript. A interface web não tem instalação npm nem build de frontend.

## Preparar o ambiente

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Trabalhar no painel cloud

Configure variáveis de ambiente para uma conta/projeto de desenvolvimento:

```powershell
$env:SUPABASE_URL = 'https://SEU_PROJETO.supabase.co'
$env:SUPABASE_PUBLISHABLE_KEY = 'SUA_CHAVE_PUBLICAVEL'
$env:MONITOR_PUBLIC_URL = 'http://127.0.0.1:8767'
.\.venv\Scripts\python.exe -m uvicorn cloud.app:app --host 127.0.0.1 --port 8767
```

Abra `http://127.0.0.1:8767`. As alterações da interface ficam em [cloud/static/](../cloud/static/); a API em [cloud/app.py](../cloud/app.py). O backend lê variáveis do processo; criar um `.env` sozinho não as carrega neste comando.

Use um projeto separado para dados de teste. O servidor na porta 8767 não inicia Chrome, Telethon nem o monitor local. Não precisa de segredo de Cron para editar a interface; ele é exigido nos endpoints agendados.

Para trabalhar no coletor, siga [Primeiros passos](getting-started.md). Evite iniciar outro monitor sobre o mesmo SQLite ou perfil de Chrome em uso.

## Testes de regressão

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node tests/test_cloud_ui.js
node tests/test_cloud_auth_ui.js
node tests/test_cloud_favorites_ui.js
node tests/test_cloud_history_ui.js
node tests/test_cloud_refresh_ui.js
```

Os testes Python e JavaScript usam dados controlados. Não comprovam que uma loja aceita scraping ou uma sessão real. [Veja os grupos de testes](../tests/README.md).

## Interface no Chrome

Com Google Chrome instalado:

```powershell
.\.venv\Scripts\python.exe tests/verify_cloud_ui.py
.\.venv\Scripts\python.exe tests/verify_notifications_ui.py
```

Esses verificadores usam Chrome real, API ASGI e banco em memória. Não enviam comandos nem ofertas fictícias para a conta de produção. O bot de notificações é simulado; nenhuma mensagem externa é enviada. Capturas ficam em `tmp/`.

## Integração PostgreSQL

Os testes `tests/cloud_*.sql` rodam em um Supabase preparado com o esquema correspondente. Execute separadamente em um projeto de teste. Eles terminam em `ROLLBACK`, incluindo fixtures e requisições pg_net; não substitua por `COMMIT`.

A lista dos arquivos e seus pré-requisitos está no [mapa dos testes SQL](../tests/README.md#postgresql).

## Verificações antes do commit

```powershell
git diff --check
.\.venv\Scripts\python.exe -m compileall -q cloud core.py monitor.py cloud_sync.py cloud_protocol.py shops.py tests
```

Rode a validação correspondente ao que mudou. Alterações apenas em documentação pedem conferência dos links, dos comandos e das referências, sem necessidade de consultar lojas reais.

Não versione dados pessoais ou artefatos de teste. [Revise as regras de credenciais](security.md#antes-de-publicar-ou-compartilhar). Use os [scripts de diagnóstico](../scripts/README.md) somente quando precisar verificar uma integração real.

## Onde documentar

- [README do projeto](../README.md): apresentação curta e primeiros passos.
- [docs/](README.md): guias atuais de uso, operação e arquitetura.
- [CHANGELOG](../CHANGELOG.md): alterações relevantes para quem usa o app.
- [docs/archive/](archive/README.md): planos e evidências históricas; não adicionar instruções atuais ali.

Mantenha um guia principal por assunto e use links para detalhes. Não duplique diagnósticos de uma sessão de trabalho no README.
