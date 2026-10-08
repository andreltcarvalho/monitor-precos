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
- [ ] Publicação e verificação autenticada.
- [ ] Revisão dos próximos atritos com evidências.

A coleta local estava indisponível em /health durante a validação. Consultas de lojas na Vercel: KaBuM retorna leituras; Pichau/Amazon/Terabyte falham na execução agendada. A interface agora evidencia esses estados.
