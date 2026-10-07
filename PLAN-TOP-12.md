# Limite de 12 promoções por peça — 2026-10-02

Escolha confirmada: mostrar somente as 12 mais baratas por peça entre todas as lojas, considerando cupom confirmado, e parar consultas automáticas de anúncios conhecidos acima do corte. Ofertas novas podem entrar quando forem mais baratas. Preservar registros, histórico, marcas, envio nacional e pagamentos.

- Catálogo: selecionar até 12 grupos após compatibilidade/deduplicação e ordenação, antes dos filtros e paginação. Empates não ultrapassam 12. Desatualizados não definem preço competitivo, mas leituras antigas dos grupos selecionados continuam disponíveis para revalidação.
- Coleta: anúncios conhecidos fora da seleção não geram leitura da página do produto nem entram na fila automática do Telegram. Descoberta de links continua; anúncio sem preço conhecido exige primeira leitura para descobrir seu valor. Preço publicado novo mais barato pode ultrapassar o corte; dados reais são salvos sem apagar os antigos.
- Validação: regressões de limite por peça, lojas, cupom, duplicados, empates, filtros, leitura vencida, salto de preço/estoque e nova candidata; simular coletor para provar que páginas caras não são consultadas. Conferir duas páginas de seis cartões no navegador real.

Áreas: core.py, monitor.py, app.py, testes e documentação. Sem dependências ou migrações adicionais.

Concluído: 14 regressões novas; suíte completa com 272 testes aprovados, compilação sem erros e detector app.py sem achados. Testes provam ausência de leituras das páginas conhecidas caras, inclusive duplicado caro de grupo barato, e rechecagem do corte na fila. Primeira leitura sem preço, queda nova, cupom desaparecendo, empate limitado e mais de 300 registros cobertos. Painel real mostra cinco peças com até 12 ofertas; RTX 5060 TI conferida nas páginas 1–6 e 7–12, com Próxima desabilitada ao final. 1280px sem overflow e console sem erros. Captura .impeccable/review/top-twelve-offers.jpg; sem alteração de filtros/configurações do usuário.
