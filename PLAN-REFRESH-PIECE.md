# Atualizar ofertas de uma peça — 2026-10-02

Escolha confirmada: buscar novas ofertas e conferir preços somente da peça escolhida, nas lojas ativas.

- Reutilizar scan_shops com component_id opcional; filtrar componentes antes de descobrir/conferir/revalidar. Manter corte de 12, marcas, envio nacional e Mercado Livre por último.
- Consulta parcial não relê cupons gerais nem altera o próximo ciclo automático do Mercado Livre para outras peças. Manual antecipa Mercado Livre apenas para a peça solicitada.
- Botão Atualizar peça no grupo expandido; estado Atualizando, bloqueio durante consulta existente, identificação da peça no status e preservação de filtros/página.
- Arquivos: monitor.py, app.py, testes e documentação. Sem migrações ou dependências.
- Validar escopo em todas as lojas, pausa de lojas/peças, corte de preços, revalidação exclusiva, horários globais e concorrência. Executar suíte/compileall/detector e conferir ação no navegador desktop.

Concluído: scan_shops aceita component_id opcional e mantém o ciclo global existente. O botão do grupo chama somente a peça selecionada, não relê feeds gerais de cupons nem muda os próximos horários globais; bloqueio desde a primeira renderização e durante qualquer consulta. Busca sem resultado nesta ação informa Nenhum anúncio encontrado para esta peça.

Validação: 280 testes na suíte completa, oito regressões específicas; compileall sem erros e detector app.py sem achados. No navegador real, clique no NV3 executou a consulta parcial, mostrou Atualizando e depois Última consulta de Kingston NV3 1 TB; busca Kingston e página 7–12 preservadas. Algumas fontes recusaram a tentativa: Amazon 503 e falha de sessão/navegador Mercado Livre; sem confirmação de novos preços nessa tentativa. Anúncios preservados e diagnósticos visíveis. Desktop 1280px sem overflow e console sem erros. Evidência .impeccable/review/refresh-piece.jpg.

Filtros temporários limpos; reinício normal para carregar versão final, PID 6128. Health running=true, Telegram conectado e log sem erros; botão individual desabilitado durante o ciclo global inicial, confirmado no navegador.
