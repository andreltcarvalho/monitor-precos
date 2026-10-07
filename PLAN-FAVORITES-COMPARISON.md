# Favoritas, comparação e ocultação

Escopo aprovado em 2026-10-02: item 5 do roadmap — salvar favoritas, comparar duas ou três ofertas e ocultar anúncios específicos.

- Banco/core: migração aditiva de `favorite`/`hidden`, preferências preservadas nas leituras e na união de URLs; anúncios ocultos saem do catálogo, consultas automáticas e alertas, sem apagar histórico.
- Apresentação: catálogo mantém top 12; favoritas e ocultas têm seleção própria com até 12 grupos por peça, em ordem de preço. Favoritas fora do corte podem ser vistas, sem mudar a prioridade automática. Preferências dos cartões se aplicam aos anúncios atualmente agrupados; outra loja/variante continua independente.
- Interface: Salvar/Salva, Comparar/Selecionada e Ocultar/Restaurar nos cartões; seletor de favoritas/ocultas. Comparação inline de até três ofertas da mesma peça, separando pagamentos, cupom, vendedor, frete desconhecido e validade. Seleção de comparação pertence à aba aberta; favoritas/ocultas persistem no SQLite.
- Validação: 12 regressões novas de migração, persistência, agrupamento, união de URL, top 12, alertas e comparação. Suíte completa: 311 testes aprovados. Compilação Python concluída. Interface real validada com favoritas após reload, tabela lado a lado, recusa da quarta seleção, lista de ocultas e restauração. Feedback após recriar cartões corrigido e revalidado no app.

Não adiciona coleta de frete, validação automática de cupons nem mudanças nas sessões das lojas.
