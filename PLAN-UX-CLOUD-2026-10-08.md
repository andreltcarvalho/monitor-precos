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
