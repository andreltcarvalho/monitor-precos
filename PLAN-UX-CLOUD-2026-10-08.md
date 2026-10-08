# UI/UX e autonomia da nuvem — 08/10/2026

## Escopo autorizado
Melhorar o painel único publicado, priorizando desktop, simplicidade, comparação de preços e detalhes sob demanda. Reduzir dependência do PC quando a coleta HTTP já funciona; sessões do Chrome, Telegram e ativação Mercado Livre permanecem locais.

## Rodada 1
- `cloud/static`: catálogo sem escolha de peça duplicada, preço e condição claros, tempo da leitura visível; cupons por estado com ações adequadas; histórico legível com tabela recolhida; fontes distinguem nuvem e PC com estado real.
- Navegação com URL, carregamento, erro recuperável e foco preservado.
- `cloud/app.py` e `cloud/collection.py`: conferência individual HTTP na nuvem, preservando observações e sem fila local para essas lojas.
- Testes de API e JS para preço, filtros, estados, falhas e histórico; validação visual em 1440 e 1024, teclado e zoom.

## Rodadas seguintes
Auditar o uso real após a primeira publicação. Resolver os maiores atritos observados, validar cada fluxo completo e publicar apenas alterações completas. Registrar evidências e limitações reais, sem assumir que testes simulados confirmam acesso às lojas.

## Referências
- Nielsen Norman Group: progressive disclosure — https://www.nngroup.com/articles/progressive-disclosure/
- W3C: mensagens de estado — https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html

## Checkpoints
- [x] Auditoria inicial do painel publicado e contratos existentes.
- [x] Implementação da primeira rodada.
- [x] 509 testes Python, regressões JS e Chrome/ASGI aprovados; imagens com dados reais em 1440/1024, sem erros JS ou overflow. Detector sem findings (aviso do caminho virtual /assets, CSS também lido como alvo).
- [x] Rodada 1 publicada em fe18012. Conferência real da KaBuM na nuvem atualizou horário/preço; API de cupons confirma estados únicos por código.
- [ ] Revisão dos próximos atritos com evidências.

A coleta local estava indisponível em /health durante a validação. Consultas de lojas na Vercel: KaBuM retorna leituras; Pichau/Amazon/Terabyte falham na execução agendada. A interface agora evidencia esses estados.

## Rodada 2 — autonomia e recuperação
- Estado desativado/reativado de cupom salvo imediatamente na nuvem e sincronizado como preferência; aplicação continua no Chrome local.
- Fontes recupera Abrir/Confirmar sessão de Mercado Livre e Shopee, com comandos validados e estado mínimo do perfil, sem exportar cookies.
- Consultas HTTP independentes e leituras da API concorrentes; resultados informam falhas e cooldown manual.
- Testes isolados de API/ponte/UI, migração restrita à lista de comandos, revisão RLS e validação em produção.

Rodada 2 validada: 50 testes cloud + JS + Chrome/ASGI aprovados; controles de sessão, preferência de cupom e cancelamento pendente cobertos. Migração `monitor_browser_session_commands` aplicada pelo plugin após teste revertido; RLS ativo e acesso anônimo recusado. Aviso Auth de proteção contra senhas vazadas é anterior e não pertence a essa migração. Coletor local iniciado: /health 200/running e raiz 307 para painel único.

## Rodada 3 — foco e coleta brasileira
Cupons com paginação e ações pertinentes à loja selecionada; atividade separa pendências do histórico. Testar região única gru1 (São Paulo) e conferir leituras reais antes de atribuir melhora. Sem proxies nem alterações de sessões.

Rodada 3: 51 testes cloud, duas suítes JS e Chrome/ASGI aprovados. Cupons paginados, filtros por loja sem ações impróprias, fila antiga preservada e renovação única de sessão. Capturas reais em 1440/1024 sem erro JS/overflow. /health confirma gru1; a mudança de região não resolveu o 403 de Pichau/Terabyte, KaBuM continua com leituras.

## Rodada 4 — recuperação e cupons públicos
Cartões alinhados e grupos com configuração recolhida. Busca pública com fontes/timeout independentes, cache exclusivo da nuvem e importação pela ponte para o aplicador; sem nova infraestrutura. Pedidos antigos em execução não podem bloquear lotes futuros indefinidamente; encerramento quando o PC pede o próximo lote, sem reenvio. Suíte completa de 523 testes aprovada antes da proteção final da fila; executar a regressão específica e validar publicação/ponte.

Rodada 4 publicada em 9fff1d0: produção confirmou 66 cupons não ML apesar das outras duas fontes com 403; ponte reiniciada com /health 200/running; pedidos em execução desde ontem encerrados sem reenvio.

## Rodada 5 — edição e critérios
Busca e remoção de marcas, campos inválidos com foco/mensagem acessível, critério de preço explícito e lista recolhida durante edição. Favoritas usam valor exibido e comparação identifica cupom antigo. Duas suítes JS e Chrome/ASGI aprovados; captura de formulário real sem erros JS/overflow. Apenas front end nesta rodada.

## Rodada 6 — histórico sem baixar todas as peças
RPC read-only `monitor_recent_observations` com SECURITY INVOKER, auth.uid(), RLS e execução anônima revogada. Consulta somente a peça/período, limitada a 10 mil leituras recentes com indicação de leitura parcial. Migração aplicada pelo plugin; teste SQL com 10.001 leituras, outra peça, data antiga e duas contas passou e foi revertido (0 fixtures restantes). EXPLAIN em dados reais: 13,685 ms, sem novo índice. 56 testes cloud e Chrome/ASGI aprovados. Comparar os pontos após publicar.

Rodada 6 publicada em 633bdce: os históricos das três peças preservaram exatamente os mesmos pontos/valores; mediana de três consultas /history/5 caiu de 4,472 s para 1,755 s (medição pontual, sem promessa de SLA). Sete páginas reais da produção verificadas no Chrome: sem erro JS, HTTP ou overflow.

## Rodada 7 — comparação e conexão
Barra de comparação com progresso e diálogo sob demanda; leitura e links de cada oferta explícitos. Timeout por tipo de operação e erro de rede legível, distinguindo resultado incerto; expiração da sessão fecha diálogos. Testes JS de timeout/rede e Chrome/ASGI de seleção, foco, fechamento e sessão expirada aprovados; captura real da comparação sem erro/overflow.

## Rodada 8 — descoberta periódica de cupons na nuvem
Compartilhar a coleta pública entre botão e endpoint agendado; Supabase Cron/pg_net usa o Vault existente a cada hora, sem Vercel Cron nem JWT administrativo. Cache privado por conta, cooldown compartilhado com o botão, fontes independentes e resposta antiga não sobrescreve atualização manual. Ativação ML permanece no PC. Validar API, função SQL com fixtures revertidas, deploy e execução real antes de habilitar o cron.

Rodada 8: 529 testes Python, dois testes JS e Chrome/ASGI aprovados. Migração aplicada pelo plugin Supabase; fixture SQL real confirmou cache, conta, timeout, atomicidade, leitura manual e cooldown, com 0 usuários de teste restantes. Habilitar e verificar coleta real após o deploy.
