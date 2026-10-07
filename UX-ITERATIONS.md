# Iterações de UX — 2026-10-01

Autorização: melhorar visual e UX sem pedir decisões, até o limite da cota de cinco horas. Desktop; preservar coleta, dados, variantes e preços crescentes por peça. Sem compras, mensagens externas ou alterações de autenticação da conta.

## Rodada 1 — acompanhar e filtrar ofertas

Escopo: app.py, presentation.py e testes existentes de apresentação, com registros neste arquivo e DESIGN.md.

- Filtros de loja e estado de conferência, com limpeza e contagem legíveis.
- Cabeçalho da peça com menor preço mostrado e limite configurado, usando dados reais.
- Horário da informação no cartão, mantendo preço conferido distinto de anunciado.
- Feedback de consulta e estados das fontes com ações claras de recuperação.

Validação: regressões de filtros e apresentação; suite e compilação; desktop real, filtros/limpeza/paginação, estados vazios, busca, detalhe, console e inspeção visual em um lote. Corrigir achados em conjunto, confirmar uma vez e avançar a outro fluxo.

Concluído: filtros combinados por loja, conferência e busca; contagem sem duplicatas; resumo de menor valor disponível, pagamento e limite; horário da informação no cartão; indicadores acionáveis e consulta desabilitada durante execução. Correção do atraso dos filtros: eventos atualizam imediatamente, em vez de depender só do timer de dois segundos. 111 testes aprovados no fechamento, compileall sem erros e detector Impeccable sem achados. Navegador real: busca Corsair abriu a seção correta; Pichau + Sem confirmação produziu estado vazio; Limpar filtros restaurou lista; navegação 1–6 / 7–12 preservada. Desktop 1440px sem transbordamento horizontal, console sem erros. Captura: .impeccable/review/ux-round-1-desktop.jpg. Inspeção visual também realizada no viewport padrão de duas colunas.

Achados para os próximos lotes: formulário mostra capacidade NV3 para qualquer peça; cancelamento de edição não é explícito; mensagens de erro são genéricas; detalhes longos usam uma única sequência; título Fonte de Alimentação perde só a palavra Fonte; faixa com um resultado ainda usa plural. Corrigir no fluxo correspondente, sem retomar polimento indefinido do catálogo.

## Próximos fluxos

Cadastro/edição de peças: campos condicionais, validação por campo, cancelamento e limites mais legíveis. Fontes: seleção/cadastro com feedback de carregamento e organização entre Telegram e lojas. Detalhes/cupons: conteúdo longo com leitura e navegação contidas. Priorizar achados observados; não criar funcionalidades sem relação com monitorar e comparar peças.

## Rodada 2 — cadastro e edição de peças

Concluído: superfície de formulário e grade desktop, capacidade só para NV3, pagamento condicionado a limite, modo de edição e cancelamento explícitos, erros por campo e validação de preços negativos/mistos e capacidade inválida, sem mexer no parser das lojas. Lista mostra também a busca configurada. Faixa de paginação usa singular para um resultado.

Validação: 120 testes aprovados (nove novos de formulário), compileall sem erros e detector sem achados. No navegador real: formulário vazio destacou nome/busca; preço -100 foi recusado sem cadastrar peça; editar NV3 mostrou capacidade 1000; cancelar limpou o modo de edição e preservou as quatro peças existentes. Captura .impeccable/review/ux-round-2-parts.jpg inspecionada. Nenhuma peça real adicionada, removida ou salva na validação. Cota após duas rodadas: 25% usados, cerca de 75% disponíveis.

## Estado do Mercado Livre

Login disponível em Chrome normal com perfil próprio. Primeira tentativa pelo navegador automatizado teve captcha ausente relatado pelo usuário e consulta 403 observada. Usuário informou que concluiu o login no Chrome. Confirmação tentou abrir a consulta, mas o Chrome do perfil do monitor ainda estava aberto, confirmado por inventário de processos. Aguardar fechamento humano dessa janela; nenhuma janela encerrada à força. Busca autenticada e coleta ainda não comprovadas.

## Rodada 3 — fontes e estados de operação

Concluído: Telegram e lojas em painéis separados; cadastro recolhível, grupos da conta pesquisáveis, exclusão das fontes já cadastradas na seleção, feedback de carregamento e botões desabilitados durante ações. Cadastro manual destaca campos obrigatórios. Remoção de fonte confirma nome e preservação das ofertas. Sessão Mercado Livre exibe passos, estado e carregamento das ações.

Validação: 123 testes aprovados no fechamento da rodada; três novos protegem identificação das fontes existentes por ID/referência, nomes iguais e fontes pausadas. Navegador real carregou 72 grupos disponíveis sem listar dados privados no relatório; cadastro vazio destacou os dois campos; cancelamento de remoção preservou cinco fontes. Desktop 1440px sem overflow horizontal e console sem erros; fim da tela acessível por rolagem. Capturas ux-round-3-sources.jpg e ux-round-3-sources-bottom.jpg. A captura fullPage contém área em branco abaixo do viewport; não foi confundida com corte real após conferir a rolagem. Cota: 37% usados ao fim da rodada.

## Rodada 4 — leitura dos detalhes

Concluído: resumo e preços no início; mensagem, anúncios agrupados, histórico e origens em expansões; corpo com rolagem e rodapé acessível; histórico inclui valor anunciado, sem pressupor pagamento. Conferência dá feedback honesto de fila. Prefixo completo Fonte de Alimentação removido apenas no título visual do cartão, com teste de regressão. O diálogo foi movido para um contêiner estável, após observar que atualização dos cartões podia fechá-lo durante leitura.

Validação: 124 testes aprovados; compilação e detector sem achados. Navegador mostrou preços e dois anúncios agrupados da INNO3D, histórico com valor anunciado e detalhe permanecendo aberto após enfileirar consulta. Desktop 1440×600: corpo 435px, conteúdo 760px com rolagem; rodapé dentro do viewport (limite inferior 555px). Console e stderr sem erros. A captura inicial dessa dimensão teve escala incorreta do navegador e não serve como prova visual final; refazer em viewport padrão na rodada seguinte.

## Rodada 5 — navegação nos cupons

Concluído: publicações em lista compacta, códigos selecionáveis e cópia com resultado confirmado pelo navegador; condições recolhíveis, busca por código/origem/condições e paginação de dez publicações. Conteúdo original e distinção de descontos não validados preservados.

Validação: 127 testes aprovados; três novos de busca/paginação protegem origens distintas, condições, acentos e esvaziamento. Compilação e detector sem erros. Navegador real: sete publicações, incluindo três recebidas de fontes Telegram; PAINELTOP filtrado e cópia confirmada pelo Clipboard API; busca sem resultado exibiu orientação; condições PRUMO5OFF completas ao expandir; limpar restaurou as sete publicações. Console sem erros. Captura ux-round-5-coupons.jpg inspecionada. Cota 43% usados após a rodada. Recepção real de cupons observada; isso não confirma leitura autenticada Mercado Livre.

## Rodada 6 — conexão e avisos

Concluído: aba Telegram mostra conexão, fontes selecionadas e última mensagem, com acesso a Fontes e instruções de autenticação recolhíveis. Instruções acompanham mudança da conexão e respeitam abertura manual enquanto o estado permanece estável. Avisos Windows em seção própria; teste impede repetição durante execução. Diagnóstico de perfil Chrome ocupado reconhece ProcessSingleton, perfil em uso e exitCode=21 sem expor erro privado do driver.

Validação: 128 testes no fechamento; novo teste de ocupação/redação do erro e estado de recuperação. Navegador mostrou conexão real, cinco fontes, ajuda recolhida e navegação imediata a Fontes. Windows aceitou pedido de aviso, sem afirmar exibição visual. Captura ux-round-6-telegram.jpg inspecionada. Sondagem real do coletor confirmou TargetClosedError com exitCode=21; nenhuma janela humana encerrada. A leitura autenticada aguarda fechamento do Chrome do monitor. Ajuste final desse marcador incluído e pendente conferência visual na rodada seguinte.

## Rodada 7 — navegação e buscas

Concluído: abas sem animação de conteúdo; busca oculta seções sem resultados e limpeza restaura as peças; espaços isolados não ativam filtros. Título principal e seções de configurações têm semântica de heading. 129 testes no fechamento e detector sem achados. Navegador: busca Corsair exibiu apenas Corsair, demais seções display:none; busca vazia apresentou orientação sem grupos repetidos; limpeza restaurou 73 ofertas. Cliques imediatos após trocar abas aceitos. Captura final de detalhes ux-round-4-details-final.jpg refeita após abertura estabilizada e inspecionada. Cota 48% usados.

## Rodada 8 — atividade das consultas

Concluído: horários de início e conclusão do ciclo no catálogo; ciclo interrompido não é apresentado como concluído. Intervalo de dez minutos continua sendo intervalo após o ciclo, sem inventar contagem regressiva. Três regressões de falhas, cancelamento e tentativa concorrente; 132 testes aprovados, compilação e detector sem achados. Navegador mostrou início real 21:22:25 e conclusão 21:23:18. Orientação específica do perfil Chrome ocupado confirmada no painel após reconhecer exitCode=21.

## Rodada 9 — conferência sem sair dos detalhes

Concluído: resumo atualiza preço, status, cupons, horário e link quando a conferência termina; histórico recebe novas leituras sem recolher a expansão. Ação fica desabilitada enquanto a oferta estiver na fila, com feedback. Fechamento elimina o diálogo e seu timer; próximo detalhe limpa a referência anterior do contêiner. Validação automatizada existente de apresentação/falhas e 132 testes aprovados. Navegador: tentativa 18:34:37 passou a 21:27:29, resultado real Pichau 403 e estado Sem confirmação, sem fechar diálogo/histórico. Fechar e reabrir manteve um único diálogo. Console e stderr sem erros; captura ux-round-9-live-detail.jpg inspecionada. Nenhum preço sintético gravado no banco do usuário. Cota 55% usados.

## Rodada 10 — idade da informação

Concluído: cartão mantém data/hora absoluta e mostra tempo desde a leitura/anúncio. Texto atualiza no timer sem recriar os cartões ou reiniciar a paginação. Tentativa falha não renova a idade do preço como se tivesse sido conferido; horário futuro/ausente é explícito. Três testes protegem limites entre minutos/horas/dias, falha e datas inválidas/futuras. 135 testes no fechamento, compilação/detector/console sem erros. Navegador exibiu leituras de 2–4 horas e anunciou a oferta não conferida pela idade da publicação; paginação 7–12 permaneceu após refreshes. Captura ux-round-10-freshness.jpg inspecionada.

## Rodada 11 — cadastro compreensível

Concluído: campo Filtro do modelo distingue busca por texto dos filtros estritos RTX 5060/CX750/NV3; descrição muda conforme seleção, sem alterar regras de matching. Fonte cadastrada é removida também das opções já carregadas, evitando seleção repetida em cache.

Validação: 135 testes, compilação/detector sem achados. Navegador editou RX 9060 e RTX 5060 sem salvar: busca por texto e filtro sem Ti explicados corretamente. Cancelamento preservou quatro peças. Carregar grupos reutilizou a lista atualizada, 72 opções e cinco fontes preservadas; console/log sem erros. Captura ux-round-11-model-filter.jpg inspecionada. Cadastro real de fonte não executado no QA para preservar as fontes do usuário; exclusão por ID/referência protegida pelos testes de seleção existentes.

## Rodada 12 — modelo e especificações legíveis

Concluído: resumo GPU separa capacidade e geração GDDR de códigos de fabricante; remove apenas sufixo técnico terminal reconhecido, sem tirar variantes após memória. Títulos longos mantêm White/Black/OC/V2 quando a truncagem cortaria esses termos. Título original permanece no detalhe, sem alterar agrupamento ou preços. Três novas regressões; 138 testes aprovados, compilação/detector sem achados. Anúncios reais Shadow/Eagle das três lojas mostraram 8GB · GDDR7 sem códigos de fabricante; Amazon Eagle passou a modelo resumido, Max preservado nas variantes correspondentes. Ordenação crescente mantida. Captura ux-round-12-model-summary.jpg. Cota 64% usados.

## Rodada 13 — contexto de ofertas parecidas

Concluído: cartões mostram vendedor quando difere da loja e quantidade de anúncios reunidos. Sem inventar vendedor desconhecido ou alterar deduplicação. Dois testes protegem vendedor ausente/próprio e contagem apenas de múltiplos anúncios; 140 testes aprovados, compilação/detector sem achados. Navegador mostrou TNTinfoLoja em anúncio Amazon e dois anúncios reunidos na INNO3D. Achado de QA: KaBuM! duplicava nome da loja por pontuação; comparação visual passou a ignorar caixa/pontuação e teste atualizado. Captura ux-round-13-seller-context.jpg, confirmação dessa correção junto da próxima rodada.

## Rodada 14 — continuidade por teclado

Achado real: Enter abriu detalhe e Escape restaurou foco corretamente enquanto o cartão não mudava; após uma conferência real recriar os cartões, foco terminava em BODY. Corrigido: fechar detalhe busca botão correspondente no cartão atual, depois cabeçalho da peça ou busca como alternativas visíveis. Sem modificar coleta ou usar preços sintéticos. Navegador repetiu consulta real, fechou com Escape e devolveu foco visível a BUTTON Detalhes; console sem erros. 140 testes e compilação/detector aprovados. Regressão é de DOM/foco, validada por interação real em vez de teste que apenas repete o seletor. Cota 70% usados durante a rodada.

## Rodada 15 — erros com ação direta

Concluído: formulário de peças e cadastro manual de fontes levam foco ao primeiro campo com erro, inclusive referência recusada pelo cadastro. Regras/valores permanecem iguais; sem salvar dados de teste. Nove testes de formulário, compilação/detector aprovados. Navegador: cadastro vazio focou Nome da peça; preço -100 focou Preço máximo; fonte vazia focou Nome da fonte; URL inválida foi recusada e focou referência. Cancelar/limpar preservou quatro peças e cinco fontes. Foco é comportamento de DOM, validado diretamente no navegador sem teste que replica run_method.

## Rodada 16 — trocar a peça pelo catálogo

Concluído: seleção Peça no toolbar permite ver um componente sem rolar pelos cartões; Todas as peças preserva a visão anterior. Seleção combina com busca/loja/conferência, limpa junto dos filtros e acompanha alterações na lista de componentes. Um teste novo cobre combinação e retorno a todas; 141 testes aprovados, compilação/detector sem achados. Navegador: Corsair exibiu quatro ofertas; com Pichau, uma; limpar restaurou 73 e todas as peças. Desktop 1440px sem overflow horizontal e console sem erros. Captura ux-round-16-piece-filter.jpg inspecionada. Cota 79% usados no início do fechamento.

## Rodada 17 — próxima ação da sessão

Concluído: indicadores do Mercado Livre usam o diagnóstico da sessão pendente em vez de forçar Login em andamento. Fechar Chrome e confirmar, verificação humana e confirmação sem anúncios legíveis têm estados próprios. Um teste cobre os diagnósticos reais e suas ações; 142 testes aprovados, compilação/detector sem achados. Navegador: indicador Fechar Chrome e confirmar abre Fontes, onde os passos e o estado pendente permanecem visíveis. Console sem erros. Captura ux-round-17-session-state.jpg. Inventário confirmou 11 processos do perfil do monitor; nenhuma janela encerrada e coleta autenticada continua pendente. Monitor reiniciado PID 20616.

## Rodada 18 — contexto dos controles

Concluído: linhas de peças/fontes têm papel de grupo e nome, contextualizando Acompanhar/Editar/Remover. Artigos de ofertas têm nome com modelo e loja. Valores atribuídos por Props, sem concatenar atributos a partir de nomes do usuário. Validação pelo DOM/acessibilidade real: grupo Kingston NV3 abriu sua edição via Enter e cancelou; grupo Ofertas Adrenaline abriu sua confirmação e cancelou, mantendo quatro peças/cinco fontes. Seis artigos exibiram nomes correspondentes aos modelos/lojas. Compilação/detector/console sem erros. Sem teste unitário que replique atributos: o comportamento relevante é a árvore acessível renderizada. Captura ux-round-18-control-context.jpg; PID 15556.

## Rodada 19 — resumo dos SSDs

Concluído em 2026-10-02: títulos NV3 reconhecidos separam capacidade e interface explícitas do nome. Formatos 2230/2280 e Mini permanecem visíveis. Nome completo, agrupamento, preço e histórico não mudam. Capacidade não é inferida de SKU/velocidade; kits, acessórios e múltiplas capacidades mantêm a descrição original. Cinco regressões novas; 147 testes aprovados e compilação sem erros. Detector final e console sem achados.

Validação real: ambas as páginas do NV3 conferidas; 1TB, 2230, 2280 e Mini legíveis, sem SKU/velocidade no resumo quando há identificação segura. Estojo RLSOCO voltou a mostrar Estojo rígido, em vez de ser resumido como SSD de 2TB. Captura ux-round-19-nv3-summary.jpg inspecionada. Reinício final PID 8744; health confirmou monitor em execução. Auditoria anterior percorreu todas as 73 ofertas das quatro peças em ordem crescente, incluindo todas as páginas.

Achado adjacente: a seleção existente aceitou um estojo Amazon cujo título cita NV3 e 500GB/1TB/2TB. Este lote protege a apresentação; não altera o matching nem exclui o registro. O valor de R$ 98,03 desse acessório não deve ser considerado preço de um SSD. Ajuste da seleção permanece pendente, assim como confirmação autenticada Mercado Livre. Usuário solicitou concluir somente esta última tarefa e parar; iterações encerradas após sua validação, sem novos lotes.


## Rodada 20 — catálogo, filtros e comparação

Concluída em 2026-10-02: toolbar secundária recolhível, filtros ativos removíveis, catálogo/favoritas/ocultas em ações visíveis, Telegram no cabeçalho. Comparação recolhida, estado preservado e opção de apenas diferenças; ocultar com Desfazer. Teclado volta ao botão recriado após um frame. Histórico movido abaixo dos cartões/paginação. Trocar filtros fecha explicitamente as outras peças, corrigindo duas expansões simultâneas observadas.

Oito regressões de apresentação adicionadas; 319 testes aprovados, compilação/detector sem achados. UI real: chip da loja removível com filtros recolhidos; comparação de duas/três preserva diferenças e expansão; ocultar/desfazer restaura a oferta; seleção por Enter recupera foco no botão Comparar. Primeiro cartão passou de 640px para 490px com painel secundário fechado. Desktop 1280px e janela 1024px (duas colunas) sem overflow horizontal; console vazio. Capturas ux-20-catalog.png e ux-20-notebook.png. PID 5192; preferências de teste revertidas, nenhum cadastro alterado.

Referências pesquisadas e plano em PLAN-UX-2026-10-02.md. Cota medida entre etapas: 21% usados. Trabalho segue para formulários e fontes.


## Rodadas 21–22 — cadastro, fontes e cupons

Lista de peças primeiro, formulário sob demanda, cancelamento/foco e rascunho protegido ao mudar de edição. Busca de fontes por nome com acentos, @referência ou ID; estado vazio recuperável, sessões recolhíveis com estado e indicadores dirigidos. Cupons com limpeza, artigos nomeados, cópia contextualizada, link sem loja identificado como link e condições conservadas ao filtrar/atualizar. Tooltip dinâmico substituído por descrição nativa; corrigido focus inexistente do QBtn.

Quatro regressões novas; 323 testes passaram, compilação/detector limpos. Navegador validou 3 de 8 fontes para promocoes e zero/limpeza; indicador Mercado Livre abriu sessão/focou no viewport. Edição alterada do water cooler foi mantida ao recusar descarte e descartada explicitamente sem salvar; query original e cinco peças intactas. Cancelar levou foco a Adicionar peça. Busca de cupons manteve condições abertas, zero/limpeza recuperou 131 publicações e focou busca. Paginação dos cartões sem novos erros após reinício, controles secundários de 32px. PID 16404, health ativo e stderr vazio. Capturas ux-21-pieces.png, ux-21-sources.png, ux-22-coupons.png.

## Rodada 23 — preço de referência e continuidade por teclado

Preço com cupom atual e menor que a base aparece em destaque com a condição explícita com cupom na sua sessão; base/pagamento permanecem separados. Valores iguais, maiores, vencidos ou indisponíveis não ganham destaque. Nenhum frete/desconto inferido; catalog_price/ranking/coleta intactos. Foco de ações de cartão é conservado se a atualização recriar o DOM, usando a mesma oferta/ação e busca como recuperação quando ela sai.

Quatro regressões novas (327 totais aprovados), compilação limpa. Teste real em duas abas: favorita temporária do NV3 acionou atualização automática da primeira aba; botão Comparar conservou foco após dois novos IDs de DOM. Favorita revertida e aba auxiliar fechada. Nenhum erro novo no console. A leitura real desta rodada não tinha cupom ativo; destaque com cupom validado por testes controlados, sem dado simulado no catálogo. Captura ux-23-keyboard.png. Cota 42% usados; monitor PID 7884. Próximo: retorno contextual da consulta individual.


## Rodada 24 — retorno contextual de atualização por peça

A peça explica consulta geral, sua atualização individual ou espera por outro componente, incluindo a loja em consulta. Resultado manual fica junto da peça com horário, leitura/pendências e diagnóstico por loja; Ver fonte abre a configuração correta. Não reutiliza conclusão de um ciclo que não iniciou e tolera recriação/remoção de widgets durante a consulta. Coleta, ordem, top 12 e agendamentos intactos.

Quatro regressões novas, 331 testes aprovados; compilação/detector limpos. Consulta individual real do Water Cooler por Enter: Pichau em andamento, depois conclusão às 20:42:42; Mercado Livre 5 anúncios, KaBuM 3, Amazon 4, Pichau sem anúncio legível e Shopee exigindo confirmação/login. Painel mostrou 3 lojas com leitura e 2 com pendências, mantendo 12 cartões. Ver fonte da Shopee abriu/focou sua sessão, sem autenticar nem alterar perfil. Log vazio; console sem erros novos. Captura ux-24-piece-result.png. PID 16516. Próximo: seleção/estados vazios e nomes acessíveis.


## Rodada 25 — seleção, vazios e diálogos por teclado

Limpar filtros conserva Favoritas/Ocultas; seleção deixa de contar como filtro. Contagem nomeia a seleção, grupos vazios deixam de se repetir e o estado vazio oferece Ver catálogo completo. Ações dos cartões recebem modelo/loja/valor no nome acessível; abrir oferta explicita nova aba. Diálogos de detalhes, remoção, descarte e encerramento têm nome/heading; fontes têm nomes de ação contextualizados.

Uma regressão nova de contagem, 332 testes totais aprovados; compilação/detector sem achados. UI real confirmou busca vazia após limpar mantendo Favoritas, sem chips/controle Limpar remanescentes, e retorno explícito ao catálogo. Cancelamento de remoção manteve cinco peças e oito fontes. Achado: Quasar retornava foco ao span interno do botão; corrigido no-refocus + retorno explícito. Confirmação final por teclado: cancelar remoção voltou aos botões Remover Water Cooler/Ofertas Adrenaline; continuar monitorando voltou a Encerrar; Fechar detalhes voltou ao botão Detalhes. Nenhuma remoção/salvamento no teste. Captura ux-25-empty-favorites.png. PID 15664.


## Rodada 26 — navegação e paginação desktop

Abas de áreas acessíveis durante a rolagem; espaço de rolagem de 64px conserva foco abaixo da navegação. Trocar página posiciona o primeiro cartão e foca seu título; próxima tecla Tab segue para as ações. Contagem da página é mensagem de estado. Regras de quantidade/ordem/pagamento intactas.

43 testes de apresentação passaram, compileall/detector limpos; última suíte completa 332 aprovada na rodada anterior, sem mudança de regras nesta rodada. Validação real por Enter: 7–12 de 12, abas entre 0–49px, primeiro cartão em 64px e título focado em 126px. 1280 e 1024×640 sem overflow horizontal; notebook com duas colunas de 456,5px. Viewport restaurado. Capturas ux-26-pagination.png e ux-26-notebook.png. PID 13968. Comparação abaixo da tela observada: resumo em -215px ao selecionar duas ofertas; próxima rodada resolve acesso sem tabela fixa.


## Rodada 27 — comparação alcançável e continuidade de foco

Resumo recolhido fica disponível sob as abas durante a rolagem, com margem de foco de 144px; tabela aberta retorna ao fluxo normal. Remover seleção conserva contexto no cabeçalho; limpar retorna à busca. Ações/switch recuperam foco quando dados selecionados atualizam a comparação. Corrigido overflow dos contêineres de abas, sem animação, que inicialmente impedia sticky interno.

332 testes totais aprovados, compilação/detector limpos. UI real: duas seleções na segunda página, resumo entre 49–111px em 1280/1024×640, controle focado em 416px sem ser encoberto e sem overflow horizontal. Tabela aberta com position static, diferenças funcionando, remoção focou cabeçalho e limpeza recuperou busca/margem de 64px. Teste de atualização entre abas preservou foco em diferenças e seu estado; favorita temporária revertida, aba auxiliar fechada. Console sem erros novos. Capturas ux-27-comparison-tray.png e ux-27-comparison-notebook.png. PID 16044.

## Rodada 28 — descoberta e paginação de cupons

Seletor conta publicações por loja (sem tratar códigos repetidos como cupons únicos), conserva escolha ao buscar e explicita que a contagem antecede a busca. Horários distinguem Publicado/Consultado; ausência de horário não recebe data inventada. Próxima/anterior focam o primeiro cupom abaixo das abas; intervalo é mensagem de estado.

Quatro regressões novas, 336 testes aprovados; compilação/detector limpos. UI real: 128 publicações, Pichau 4, Mercado Livre 101, KaBuM 1, Amazon 8, Shopee 7, AliExpress 2 e loja desconhecida 5. Busca SKRP10 filtrou uma publicação mantendo Pichau; limpeza voltou a todas. Telegram mostrou Publicado, oficial sem timestamp mostrou Horário não informado; Consultado validado em fixture. Enter na próxima página mostrou 11–20, primeiro artigo em 64px e heading focado em 85px, abas terminando em 49px, sem overflow. Captura ux-28-coupons.png. PID 21076.

## Rodada 29 — estabilidade durante leitura de cupons

Atualização da lista é adiada se interromperia condições abertas na página visível. Aviso oferece Atualizar lista; dados continuam sendo coletados. Atualização explícita foca início da página; trocar busca/página também carrega os dados recentes. Condições de páginas/filtros diferentes não bloqueiam a chegada inicial de atualizações. Código/condições não são modificados.

Cinco regressões novas, 341 testes aprovados; compilação/detector limpos. UI real confirmou condições expandidas, texto e filtros/paginação preservados, banner inicialmente ausente. Não houve nova publicação durante esta inspeção: retenção/contagem de novidades foi validada em testes controlados. PID 21652.

## Rodada 30 — interpretação do histórico

Explicação e título seguem pagamento selecionado; método distingue Pix, total no cartão, preço sem pagamento informado e melhor preço incluindo cupom. Regras gerais em Como interpretar este histórico. Descrição do gráfico em português, com peça, pagamento, datas/valores e lacunas sem estimativa. Cálculos e observações intactos.

Três regressões novas, 344 testes aprovados; compilação/detector limpos. UI real confirmou Pix, melhor preço e total no cartão, descrição acessível contextualizada e ajuda abrindo. Captura ux-30-history.png. Achados da inspeção: eixo ainda formatava milhar em inglês e cabeçalho não identificava peça. Correção final implementada, aguardando restart/uma confirmação. Navegação manual entre abas preservava posição anterior e deixava Cupons encontrados em -118px: próxima rodada resolve. Rascunho de validação descartado sem salvar; campos corrigidos já limpam erro nativamente, nenhuma alteração adicional de formulário necessária.

Confirmação final da rodada 30: cabeçalho identifica Kingston NV3 1 TB e eixo apresenta R$ 1.200,00, R$ 1.000,00 etc. Gráfico inteiro e foco visível na captura ux-30-history-final.png; 1280 e 1024×640 sem overflow, viewport restaurado. Nenhuma alteração de dados do histórico.

## Rodada 31 — entrada de área previsível

Ativar aba por clique/Enter/espaço retorna ao início da área, sem afetar atalhos programáticos para loja. Setas continuam com navegação nativa de foco; ativação é explícita. JS restrito à navegação, sem mudança de consulta/estado dos filtros.

Compilação/detector limpos; última suíte 344 aprovada. Validação real do achado: Cupons encontrados foi de -118px para 193px com scrollY zero. Enter abriu Fontes com foco na aba. Atalho Shopee preservou destino: sessão focada em 240px, abaixo das abas. Setas moveram foco sem mudar aba selecionada. Teste específico é interação real/posição DOM; não foi criado teste estático que apenas espelhasse o listener. PID 10828.

## Rodada 32 — proteção de rascunho ao sair

beforeunload instalado apenas enquanto campos efetivos diferem da base. Trocar área mantém proteção; cancelar/salvar/desfazer edição a remove. Não grava rascunhos em armazenamento nem altera autenticação.

12 regressões existentes de rascunho/validação passaram, compilação/detector limpos. UI real: rascunho temporário permaneceu após tentativa de recarga, tanto em Peças como após ir para Fontes. Reverter Nome ao valor inicial retirou a proteção e recarga abriu Ofertas normalmente. API de diálogo retornou undefined: preservação da página/valores observada, mas texto visual da confirmação nativa não foi capturado pelo navegador incorporado. Captura ux-32-draft.png. Nenhuma peça foi salva/removida. PID 10828.

## Rodada 33 — identidade das condições e foco no vazio

Identificação de cupons de sites deixa de usar posição na lista: código/link/origem conservam condições do mesmo cupom quando resultados mudam de ordem. Ativações sem código conservam origens distintas. Se atualizar a lista resultar em vazio, foco retorna à busca.

Três regressões novas, 347 testes aprovados; compilação/detector limpos. Mudança de ordem/inserção/texto/ativação sem código coberta em testes controlados. Processo PID 20732 aplicado; leitura de uma publicação Telegram mantida aberta para observar a atualização real do cache público. Validação nativa final em andamento.

Confirmação real das rodadas 29/33: após consulta pública concluída, Atualização da lista disponível apareceu e artigo c1060/mensagem DAN TECH 129669 permaneceram iguais, com condições abertas. Atualizar lista por Enter ocultou o aviso, carregou artigo c4858 com a mesma publicação e focou seu heading em 85px, primeiro artigo em 64px. Captura ux-33-reading-update.png. Pichau ff10 manteve chave por URL/código e condições abertas após filtrar; filtros de teste limpos. Nova publicação/evento Telegram não foi observado nessa confirmação; o evento real foi atualização de cache público.

## Rodada 34 — retorno de foco ao limpar fontes

Achado real: Enter em Limpar busca restaurava oito fontes, mas o foco ia para BODY. Corrigido retorno ao input estável da busca, conservando estados/lista. 30 testes de UX passaram, compilação/detector limpos; validação nativa da correção pendente de restart. Nenhuma mudança de dados/consulta.

Confirmação da rodada 34: Enter em Limpar busca retornou ao input Buscar nas fontes, valor vazio e oito fontes ativas. Editar/cancelar Water Cooler conservou query water cooler rise mode 360 argb e cinco peças; rascunho inicial sem alterações não ativou guard. Suíte completa final: 347 testes em 24,188s, OK. PID 12544.

## Rodada 35 — foco após desmontagem das abas

Revisão de console encontrou observadores usando contêiner removido quando Ofertas não estava montada: observe(null) e contains(null). Corrigido ciclo de vida: observação da superfície estável do documento, resolução do contêiner atual por ID e guarda de existência/visibilidade. Restaurar continua restrito à ação acompanhada quando ela foi removida e BODY recebeu foco; não interfere em outra área.

Compilação/detector limpos; última suíte completa 347 aprovada. Confirmação real após sair/voltar a Ofertas: favorita de oferta 168 alterada numa aba auxiliar provocou recriação, mas foco permaneceu em Comparar/168 na aba principal. Favorita revertida, comparação limpa e aba auxiliar 10 fechada. Nenhum erro novo de console desde 00:56:35 UTC. PID 16416 com health running=true/Telegram configurado; stderr registrou WinError 10054 de conexão remota no asyncio, sem encerrar o monitor. Não houve alteração de coletor para esse registro. Catálogo final e histórico nas capturas ux-final-catalog.png/ux-30-history-final.png; viewport restaurado e dados de teste não persistidos.
