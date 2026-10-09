# Shopee nas fontes — 2026-10-02

Confirmado: busca e conferência de preços, usando Chrome próprio da Shopee; login humano pela aba Fontes.

- Novo coletor de navegador com perfil restrito em data/shopee, abertura humana no Chrome normal e confirmação por busca de uma peça ativa. Sem exportar cookies nem usar a sessão pessoal.
- shops.py: loja, domínios/encurtador, links de produto, descoberta e preço do produto. Sem inferir Pix ou aplicar cupons publicados.
- app.py: controles de sessão seguindo o padrão existente; indicadores/filtros aproveitam SHOP_NAMES.
- Preservar top 12, marcas, lojas pausadas, consulta individual e Mercado Livre por último. Sem novas dependências/migração.
- Testar domínios/redirecionamentos, identificação, preços/ranges, login/bloqueios, sessão e ciclo de coleta. Validar UI real; coleta autenticada depende do login humano.

Implementado sem migração/dependências: shopee_browser.py, roteamento/parsing em shops.py e controles em app.py. Fonte ligada por padrão como as demais, consulta antes do Mercado Livre, perfil restrito separado e confirmação apenas com anúncios da peça ativa. Intervalos de variação são recusados.

Validação: 297 testes aprovados (13 específicos Shopee), compilação sem erros e detector app.py []. Página pública real exigiu Login Necessário; HTTP devolveu shell sem ofertas. Não declarar preços reais autenticados validados. Painel real mostrou fonte ligada, controles e exigência de fechar janela humana antes de confirmar. Chrome do perfil próprio aberto; login/confirmacão ainda pendentes. Desktop 1280px sem overflow, console/log sem erros; health e Telegram ativos, PID 18404. Captura .impeccable/review/shopee-source.jpg. Nenhum preço simulado inserido no banco real.

Usuário informou login efetuado, mas confirmação sem peças. Diagnóstico do coletor real: página Tente Novamente Mais Tarde, zero links de produto e zero resultados compatíveis. Corrigida classificação desse bloqueio antes de buscar/preçar produtos; nenhuma remoção do perfil/login. Nova regressão e suíte final 298 aprovados, compileall sem erros. Reinício PID 12128; coleta de preços Shopee continua bloqueada externamente, não marcar sessão como confirmada nem declarar integração autenticada validada.

Confirmação posterior revelou redirecionamento real para /verify/captcha, que podia estar sem texto ao ler o HTML. Agora o destino de verificação também é identificado independentemente da hidratação da página. Suíte final 299 testes, compilação sem erros; monitor PID 22000. Mensagem de bloqueio finalmente confirmada no botão real em Fontes, sem erro de console. A fonte foi integrada, mas a busca de preços continua pendente da liberação externa; não confundir cadastro da fonte com preços autenticados funcionando.
