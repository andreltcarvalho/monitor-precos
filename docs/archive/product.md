# Monitor de peças

<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
Python, Telethon, NiceGUI, SQLite, HTTPX; Playwright com Google Chrome e perfil próprio para consultas autenticadas do Mercado Livre.

## Users
Uma pessoa acompanhando compras pessoais, incluindo peças de PC e anúncios locais de outros produtos, no Windows.

## Product Purpose
Receber ofertas recentes das peças selecionadas, comparar Pix e parcelamento, encontrar cupons e acompanhar buscas de usados na OLX.

## Operating Context
Uso local no PC, painel no navegador e processo de monitoramento independente da aba. Grupos do Telegram selecionados pelo usuário; lojas Mercado Livre, Pichau, KaBuM, Amazon e Shopee. Bloqueios de leitura pública são informados sem inventar preços.

## Capabilities and Constraints

OLX: área Usados independente do ranking de peças, com cadastro por URL de busca ou produto/UF/cidade. Teto e exclusões de título opcionais. Ler até 50 anúncios recentes a cada dez minutos, identificar pelo ID e guardar preços observados no SQLite. Primeira leitura sem avisos do acervo; depois, novos anúncios e quedas dentro dos filtros. Pausa, consulta manual e histórico por anúncio. HTTP primeiro, Chrome próprio quando necessário; cidade resolvida pelo seletor oficial. Bloqueio não vira busca vazia. Ausência não confirma venda; conservação, pagamento e frete não inferidos. Pode conter produtos novos. Facebook fora deste lote.

Favoritas/comparação/ocultação: favoritas e ocultas salvas por anúncio no SQLite, preservadas por atualizações e união de URLs. Cartão aplica a escolha aos seus anúncios agrupados atuais; outras lojas/variantes independentes. Ocultos deixam catálogo, consultas automáticas e alertas, conservando histórico, com restauração na aba Ofertas. Catálogo mantém as 12 mais baratas; seleções próprias exibem até 12 favoritas/ocultas por peça. Favoritar não força monitoramento acima do corte. Comparação por aba aberta, até três ofertas da mesma peça, pagamentos e cupom separados, sem inventar frete/condições desconhecidas; remoção/ocultação retira a oferta da comparação.
Lista inicial: RTX 5060 de fabricante variável, Corsair CX750 e Kingston NV3 de 1 TB. Avisar apenas ofertas entre os 10% mais baratos da mesma peça e pagamento, com limite individual opcional adicional. Não tratar dados anunciados como preço confirmado. Não importar histórico antigo para alertas. Não expor credenciais no chat.

Limite confirmado: mostrar no máximo 12 ofertas por peça entre todas as lojas, depois de agrupar duplicados e ordenar pelo preço efetivo, antes dos filtros/paginação. Empates não ultrapassam 12; estoque esgotado e marcas ignoradas ficam fora. Anúncios conhecidos acima do corte deixam descoberta, fila automática e revalidação de páginas de produto. Dados e histórico continuam salvos; nova publicação mais barata pode recolocar um anúncio na seleção. Link novo sem preço conhecido precisa da primeira leitura. Corte de revalidação usa último preço base conhecido para leituras vencidas, ignorando cupom vencido; preços antigos continuam fora da comparação/avisos. Conferência manual é preservada. Avisos nunca excedem a seleção atual de 12, mantendo a regra dos 10% e os limites de pagamento. Não limitar a amostra aos 300 registros mais recentes, para preservar ofertas baratas antigas.

Regra de atratividade confirmada em 2026-10-02: considerar as ofertas salvas da peça, inclusive a candidata, com preço positivo no pagamento comparado e sem indisponibilidade explícita. Agrupar anúncios repetidos como no catálogo e usar o menor valor desse pagamento em cada grupo. A faixa contém ceil(N/10) posições, pelo menos uma; preços empatados no corte também qualificam. Com teto, usar o pagamento escolhido; sem teto, Pix quando informado, senão total no cartão, senão preço anunciado. Comparar sempre a mesma condição, sem presumir Pix ou aplicar cupons não validados. Ofertas fora da faixa continuam salvas e conferidas, sem aviso.

Identificação: acessórios e kits ficam fora da seleção de peças; buscas por texto que pedem explicitamente um acessório/kit continuam possíveis. NV3 exige capacidade explícita e rejeita anúncios que misturam capacidades. A identidade confirmada pela loja prevalece sobre a publicação do Telegram. Registros antigos incompatíveis permanecem no banco, sem participar do catálogo, histórico ou ranking de avisos.

Marcas: reconhecer fabricantes conhecidos e aliases pelo texto, sem adivinhar quando houver ambiguidade. Cada peça pode ignorar marcas escolhidas pelo usuário; aplicar à coleta, catálogo e avisos, preservando registros e histórico salvos. Nenhuma exclusão padrão. Marcas desconhecidas continuam visíveis.

Cupom da sessão Mercado Livre: guardar somente preço monetário explícito com cupom menor que o preço principal, dentro da área do produto e visível. Mostrar separado e usar o menor valor na ordenação e agrupamento do catálogo. Sem Pix explícito, mostrar preço anunciado como principal e total parcelado separado. Não inferir desconto de percentual, publicidade de cartão ou produtos recomendados; nova leitura sem cupom remove o valor atual. Salvar cupom em cada observação, incluindo mudanças no mesmo dia, sem reconstrução retroativa. Histórico adiciona melhor preço incluindo cupom, comparando condições distintas e mantendo pagamentos originais separados. Avisos e referência de queda usam o cupom confirmado no pagamento não informado; esse valor não atende teto exclusivo Pix/cartão sem condição conhecida.

Validade de leitura: 30 minutos nas demais lojas, 90 minutos no Mercado Livre e cinco minutos para anúncio não conferido do Telegram. Falha não renova validade nem apaga histórico. Preço vencido deixa comparações, mínimo do grupo e corte de avisos; registro continua no catálogo, ao fim, com indicação de desatualização. Conferir até quatro anúncios vencidos por peça/loja que não apareceram na descoberta, respeitando intervalo e prioridade da loja.

Cupons publicados: separar loja identificada dos links e fonte; preservar entidades/URL da publicação Telegram. Inferir apenas domínios/encurtadores conhecidos, destinos explícitos em parâmetros e nomes inequívocos no texto. Filtro por loja, código copiável, condições e links de uso/origem. Além de Telegram/Pichau oficial, ler tabelas públicas Melhores Cartões a cada 30 minutos antes do Mercado Livre; tabelas com indicador de atividade aceitam apenas entradas ativas. Falha conserva cache, exposto por até 12 horas. Publicação não confirma aplicabilidade nem desconto; não navegar pelos links de compra automaticamente.

Agendamento: Pichau, KaBuM, Amazon e Shopee a cada dez minutos; cupons Pichau antes do Mercado Livre. Mercado Livre por último e no máximo a cada trinta minutos no ciclo automático; consulta manual antecipa. Descontar duração do ciclo da espera para não somar o atraso das consultas ao intervalo.

Shopee: Chrome próprio com perfil restrito e login humano na aba Fontes, sem importar cookies. Confirmar sessão somente após fechar a janela humana e encontrar anúncios legíveis de uma peça ativa. Descoberta de links de produto e encurtadores suportados, leitura de preço estruturado em BRL e pagamento desconhecido; não confirmar intervalos de variações como um preço único nem inferir Pix/cupons. Erros mantêm sessão/anúncio. Os ciclos, consultas por peça, pausa da loja, filtros e top 12 incluem a Shopee. Coleta autenticada real depende do login e da validação do layout após ele.

Atualização por peça: na aba Ofertas, cada grupo oferece Atualizar peça. Descobrir e conferir somente o componente escolhido nas lojas ativas, incluindo Mercado Livre por último e mantendo corte de 12, marcas e origem nacional. Consulta parcial não relê cupons gerais nem altera os próximos horários globais do Mercado Livre/cuponagem. Nenhuma consulta sobreposta; botão mostra Atualizando e status identifica a peça. Peça pausada/removida não inicia coleta. Filtros, página e histórico preservados; consulta global continua disponível.

Mercado Livre somente com envio local: seguir o link do filtro Local quando fornecido pela busca, sem aceitar redirecionamento que perca esse filtro. Quando a página não oferece Local, descobrir candidatos e exigir confirmação nacional individual na área de compra do produto. Excluir cartões internacionais, sem usar menu ou recomendações como evidência. Origem desconhecida permanece excluída do catálogo, comparações e avisos até confirmação. Migração mantém registros e observações antigos; outras lojas não são afetadas.

Histórico por peça: menor preço e mediana dos menores preços diários em 7/30 dias, somente nas leituras de loja e sem frete. Pagamentos originais excluem cupom; a opção de melhor preço considera o desconto confirmado de cada observação. Dias locais de calendário, incluindo hoje; não preencher dias sem leitura nem usar falhas de conferência como preços novos. Guardar estoque em cada nova observação e excluir leituras explicitamente esgotadas, preservando preços de quando o anúncio estava disponível. Observações antigas ficam com estoque desconhecido, sem inferir retroativamente. Pagamentos separados: Pix, total no cartão e preço sem pagamento informado (este último só quando a observação não identifica Pix/cartão). Mostrar quantidade de dias observados e histórico curto abaixo de três dias. Preço constante deve gerar uma observação ao menos a cada novo dia de consulta. Filtros do catálogo não alteram essas estatísticas.

Avisos explicados: informar única oferta comparável, novo menor preço entre concorrentes ou posição na faixa dos 10%. Comparar com a mediana de 30 dias apenas com três dias observados. Repetir o mesmo anúncio/modelo na mesma loja e vendedor somente com queda de pelo menos 2% sobre o último preço notificado na mesma condição, ainda na faixa e respeitando o teto. Alterações de cupom não validado/parcelas, aumentos e pequenas quedas não renovam a referência; falha de envio também não. Se a primeira confirmação esclarecer o pagamento de um aviso já enviado, guardar essa leitura como referência sem outro aviso e exigir 2% de queda a partir dela. Migração aditiva recupera referências antigas pela última observação anterior ao registro de aviso; sem leitura recuperável, preservar a supressão do anúncio legado. Novos registros distinguem envio aceito e referência de confirmação. Não declarar exibição visual do toast apenas por aceitação da chamada pelo Windows.

Mercado Livre: usuário abre a janela de login pela aba Fontes no Chrome normal, entra na conta, fecha essa janela e confirma uma busca. Perfil próprio salvo neste PC, sem importar cookies do navegador pessoal. Um 403 sem janela permite uma tentativa com janela no mesmo perfil; após sucesso, esse modo é lembrado. Consultas pausam durante login; pedidos de login e verificação humana exigem voltar à janela.

## Brand Commitments
Interface simples e prática; o usuário não quer um software sofisticado ou um processo extra de escolha visual.

## Evidence on Hand
Design aprovado em ../DESIGN-MONITOR-PRECOS.md. Telegram autenticado e recepção real de publicações de cupons observada. Mercado Livre autenticado e leituras reais com cupom verificadas no perfil próprio com janela. Interface desktop validada por lotes documentados em UX-ITERATIONS.md e CHECKPOINT.md.

## Product Principles
- Avisar rapidamente e conferir a loja depois.
- Mostrar a origem, o horário e os limites de cada informação.
- Evitar avisos repetidos.
- Manter dados e sessão locais.
