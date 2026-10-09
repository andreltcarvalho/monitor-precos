# Mercado Livre — coleta pela busca, 2026-10-07

Escolha confirmada: usar os cartões da busca como fonte principal e abrir o produto somente quando faltar informação necessária. Conferência manual continua lendo o produto.

- `shops.py`: extrair título/link, vendedor, preço principal, parcelas explícitas e preço com cupom dos cartões; ignorar preço anterior, promoções de saldo e outra opção de compra. Reutilizar filtro Local, sem presumir origem ou Pix.
- `monitor.py`: salvar leituras completas diretamente; consultar produto para candidatos incompletos. Usar preço novo da busca na decisão das 12, preservando filtros, histórico, avisos e intervalo/ordem do Mercado Livre.
- Validar regressões de separação dos preços, origem, pagamento exigido, queda de oferta conhecida fora do corte, falta de dados e ausência de navegações desnecessárias. Executar suíte e consulta real pelo coletor normal, com o perfil próprio do monitor.

Concluído: 15 regressões novas, 461 testes gerais aprovados, compilação limpa. Consulta real pelo fluxo do monitor em banco isolado, sem teto por pagamento: 12 ofertas nacionais com cupom, duas navegações e nenhuma página de produto. Cadastros reais preservados; monitor principal reiniciado.
