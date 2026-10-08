# UI/UX e autonomia da nuvem â€” 08/10/2026

## Escopo autorizado
Melhorar o painel Ãºnico publicado, priorizando desktop, simplicidade, comparaÃ§Ã£o de preÃ§os e detalhes sob demanda. Reduzir dependÃªncia do PC quando a coleta HTTP jÃ¡ funciona; sessÃµes do Chrome, Telegram e ativaÃ§Ã£o Mercado Livre permanecem locais.

## Rodada 1
- `cloud/static`: catÃ¡logo sem escolha de peÃ§a duplicada, preÃ§o e condiÃ§Ã£o claros, tempo da leitura visÃ­vel; cupons por estado com aÃ§Ãµes adequadas; histÃ³rico legÃ­vel com tabela recolhida; fontes distinguem nuvem e PC com estado real.
- NavegaÃ§Ã£o com URL, carregamento, erro recuperÃ¡vel e foco preservado.
- `cloud/app.py` e `cloud/collection.py`: conferÃªncia individual HTTP na nuvem, preservando observaÃ§Ãµes e sem fila local para essas lojas.
- Testes de API e JS para preÃ§o, filtros, estados, falhas e histÃ³rico; validaÃ§Ã£o visual em 1440 e 1024, teclado e zoom.

## Rodadas seguintes
Auditar o uso real apÃ³s a primeira publicaÃ§Ã£o. Resolver os maiores atritos observados, validar cada fluxo completo e publicar apenas alteraÃ§Ãµes completas. Registrar evidÃªncias e limitaÃ§Ãµes reais, sem assumir que testes simulados confirmam acesso Ã s lojas.

## ReferÃªncias
- Nielsen Norman Group: progressive disclosure â€” https://www.nngroup.com/articles/progressive-disclosure/
- W3C: mensagens de estado â€” https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html

## Checkpoints
- [x] Auditoria inicial do painel publicado e contratos existentes.
- [x] ImplementaÃ§Ã£o da primeira rodada.
- [x] 509 testes Python, regressÃµes JS e Chrome/ASGI aprovados; imagens com dados reais em 1440/1024, sem erros JS ou overflow. Detector sem findings (aviso do caminho virtual /assets, CSS tambÃ©m lido como alvo).
- [x] Rodada 1 publicada em fe18012. ConferÃªncia real da KaBuM na nuvem atualizou horÃ¡rio/preÃ§o; API de cupons confirma estados Ãºnicos por cÃ³digo.
- [ ] RevisÃ£o dos prÃ³ximos atritos com evidÃªncias.

A coleta local estava indisponÃ­vel em /health durante a validaÃ§Ã£o. Consultas de lojas na Vercel: KaBuM retorna leituras; Pichau/Amazon/Terabyte falham na execuÃ§Ã£o agendada. A interface agora evidencia esses estados.

## Rodada 2 â€” autonomia e recuperaÃ§Ã£o
- Estado desativado/reativado de cupom salvo imediatamente na nuvem e sincronizado como preferÃªncia; aplicaÃ§Ã£o continua no Chrome local.
- Fontes recupera Abrir/Confirmar sessÃ£o de Mercado Livre e Shopee, com comandos validados e estado mÃ­nimo do perfil, sem exportar cookies.
- Consultas HTTP independentes e leituras da API concorrentes; resultados informam falhas e cooldown manual.
- Testes isolados de API/ponte/UI, migraÃ§Ã£o restrita Ã  lista de comandos, revisÃ£o RLS e validaÃ§Ã£o em produÃ§Ã£o.

Rodada 2 validada: 50 testes cloud + JS + Chrome/ASGI aprovados; controles de sessÃ£o, preferÃªncia de cupom e cancelamento pendente cobertos. MigraÃ§Ã£o `monitor_browser_session_commands` aplicada pelo plugin apÃ³s teste revertido; RLS ativo e acesso anÃ´nimo recusado. Aviso Auth de proteÃ§Ã£o contra senhas vazadas Ã© anterior e nÃ£o pertence a essa migraÃ§Ã£o. Coletor local iniciado: /health 200/running e raiz 307 para painel Ãºnico.

## Rodada 3 — foco e coleta brasileira
Cupons com paginação e ações pertinentes à loja selecionada; atividade separa pendências do histórico. Testar região única gru1 (São Paulo) e conferir leituras reais antes de atribuir melhora. Sem proxies nem alterações de sessões.
