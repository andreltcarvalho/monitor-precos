# Alterações

## 2026-10-08

- Desativar/reativar cupons passa a funcionar imediatamente na nuvem, com preferência diária sincronizada e resultados de aplicação preservados. Fontes recupera abrir/confirmar sessões próprias de Mercado Livre e Shopee pelo PC, expondo somente estado do perfil; comandos novos mantêm RLS por dono. Pedidos pendentes podem ser cancelados antes de recebidos, com condição atômica; histórico distingue Cancelado de Falhou. Consultas HTTP independentes executam em paralelo e informam motivos de falha; botão da peça indica o cooldown manual. Migração restrita à lista de comandos validada em transação revertida, sem alteração de permissões. 50 testes específicos e fluxos Chrome/ASGI aprovados.

- Painel único refinado: seleção de peça sem controle duplicado, cartões com preço/condição e idade da leitura, detalhes sob demanda, navegação com URL e recuperação de carregamento/erro. Cupons abre no Mercado Livre, mostra estados e quantidades, distingue loja/publicação e impede lotes repetidos na fila. Histórico usa datas reais, mostra valores nos pontos e não interpola dias sem leitura; tabela recolhida. Fontes distingue nuvem/Chrome e resultados de consultas. Conferência individual das lojas HTTP passa a rodar na nuvem com observação persistida; falhas preservam o preço sem confirmação. Código repetido em várias fontes mantém um único resultado salvo de ativação.

- Melhores Cartões removido dos cupons do Mercado Livre, incluindo cache e tentativas antigas nas listas e lotes. Resultados anteriores de ativação são preservados quando o mesmo código aparece em uma fonte válida. Pelando integrado por HTTP com código explícito, estado ativo, publicação no dia de São Paulo e condições para todo o site ou informática/eletrônicos; selecionados sem categoria, outras categorias, primeira compra, antigos e duplicados são descartados. 225 testes específicos aprovados e compilação limpa; coleta real encontrou um cupom relevante do Mercado Livre entre 82 publicações do Pelando.

## 2026-10-07

- Painel cloud reorganizado para desktop: navegação lateral, seleção de peça, seis cartões por página mantendo as 12 mais baratas, modelo/specs resumidos e preço/pagamento em destaque. Favoritos por estrela, comparação recolhida e informações completas no diálogo. Peças abre na lista, cadastros de peças/grupos/OLX sob demanda; cupons mostram loja/estado e preservam condições abertas. Diretrizes de divulgação progressiva NN/g e estrutura W3C aplicadas. 495 testes Python aprovados, regressões JavaScript e validação isolada pelo navegador; coleta, histórico, credenciais e dados locais preservados.

- Consultas HTTP automáticas via Supabase Cron/pg_net e endpoint autenticado na Vercel, sem Vercel Cron ou chave administrativa na aplicação. Até dois lotes peça/loja por minuto, intervalo mínimo de dez minutos, pausas/exclusões e consultas manuais respeitadas. Persistência de histórico por conta, proteção contra leituras antigas, encerramento de timeouts e preservação das ofertas em falhas. 494 testes aprovados e testes SQL transacionais revertidos; ciclo real em produção salvou cinco leituras da Amazon e confirmou execuções automáticas do Cron. Mercado Livre, Shopee, OLX, Telegram e aplicação de cupons continuam locais.

- Preparação para Vercel: `windows-toasts` fica restrito ao Windows, evitando a instalação de WinRT no Linux. `.vercelignore` exclui bancos, sessões, credenciais, arquivos temporários e metadados locais; `.vercel/` também é ignorado no Git. CLI autenticada e checkout vinculado ao projeto existente. Marcador de plataforma e exclusões verificados; 24 testes do monitor aprovados. Migração do painel/banco e novo deploy ainda pendentes.

- Mercado Livre coleta preços diretamente dos cartões da busca: preço atual, vendedor, parcelas explícitas e preço com cupom, sem misturar preço anterior, saldo Mercado Pago ou outra opção de compra. Abre produto somente quando faltar preço, origem nacional ou pagamento exigido pelo teto; conferência manual preservada. Até 12 candidatos ordenados por preço com cupom, usando preço novo para reavaliar ofertas conhecidas fora do corte. 15 regressões novas; 461 testes aprovados e compilação limpa. Fluxo real com sessão própria e banco isolado, peça sem teto por pagamento: 12 ofertas nacionais e 12 preços com cupom, duas navegações (busca e Local), nenhuma página de produto. Cadastros de produção preservados.

- Corrigida busca OLX por Piracicaba/SP quando o seletor de localização está indisponível: URL municipal direta, preservando consulta, preço máximo e categoria, aplicada também a cadastros existentes e ao botão/link de abertura. HTTP e Chrome confirmam a cidade pelo título de destino; nome da cidade no texto pesquisado não basta. Recomendações de outros municípios são descartadas antes de salvar. Seis testes novos, 28 específicos e 446 gerais aprovados; compilação limpa. Consulta real pelo Chrome confirmou a rota municipal, sem anúncios locais de “rtx 5060 ti” na leitura; monitor reiniciado e cadastro original consultado com sucesso.

## 2026-10-06

- Catálogo Mais baratas respeita o preço máximo da peça no Pix ou total no cartão, inclusive no valor igual ao limite. Filtra antes de agrupar duplicatas e selecionar as 12; alterar/remover o limite atualiza a apresentação sem nova coleta ou exclusão de histórico. Preço desconhecido no pagamento escolhido não passa pelo teto, e Favoritas/Ocultas preservam acesso aos registros. Seis regressões novas e mensagens de vazio/hint ajustadas ao limite.

- Aplicador segue para o próximo cupom após “Tivemos um problema”, preservando a pendência para retentativa. Cinco respostas consecutivas desse erro pausam o lote até o próximo ciclo horário; outra resposta zera a contagem e cada lote começa do zero. Demais bloqueios/pendências mantêm a interrupção existente. Três regressões novas cobrem continuidade, limite em lotes normais/de falhas, próxima execução e reset por sucesso/já existente/recusa.

- Cupons limitados ao dia atual de São Paulo. Data de descoberta persistida separadamente da tentativa; caches não renovam essa data a cada consulta. Publicações, caches e resultados anteriores apagados definitivamente, sem arquivo ou retentativa individual. Lotes normais e de falhas revalidam o corte antes de cada envio, inclusive na virada do dia. Aba informa descoberta e regra diária. Sete regressões novas; 431 testes aprovados e compilação limpa. Limpeza real removeu 116 publicações, 18 registros de aplicação e 4 cupons oficiais antigos; monitor reiniciado e interface conferida.

- Corrigida interrupção da fila após redirecionamento de sucesso para `/cupons/active?source_page=int_input_code`: a navegação ocorrida após enviar o código confirma a inserção mesmo quando a mensagem desaparece, e reabre imediatamente a página inicial. Sucesso oficial também reabre imediatamente, sem repetir o código. Feedback técnico “spinner” é ignorado; recusa explícita continua prevalecendo, e falha de reabertura não desfaz sucesso confirmado. Quatro regressões novas, 40 testes específicos e 424 gerais aprovados, compilação limpa. Revalidação real de SEMDEMORA substituiu pendência “spinner” por já existente; redirecionamento de uma inserção nova foi validado por simulação.

- Cupons do Mercado Livre reunidos por código, com filtros Novos/Ativados/Falhas/Desativados, tipo de falha, resposta da loja, horário e tentativas. Retentativa individual ou somente das falhas recuperáveis, mantendo o ciclo horário. Desativar/reativar persiste sem apagar resultados e respeita códigos ainda na fila; recusas definitivas não são reenviadas, incluindo a mensagem “esgotou”. Se um sucesso levar a Meus cupons sem campo/botão de inserção, o próximo código reabre a página inicial, preservando a confirmação anterior; recusas com controles disponíveis não recarregam. Migração aditiva e doze regressões novas; 420 testes aprovados, compilação e detector limpos. Interface real validou busca, estados, filtros, desativação/reativação preservando histórico; redirecionamento após sucesso validado em simulação, sem novo lote externo.

- Adicionada aba Usados com buscas OLX por link ou produto/UF/cidade, teto/exclusões opcionais, consulta a cada dez minutos, pausa e histórico. Primeira leitura estabelece referência; avisos posteriores de novos anúncios e quedas. HTTP direto recusado com 403 na validação; Chrome próprio leu 22 anúncios por campos e 26 por URL. 22 regressões OLX e 408 testes gerais aprovados; compilação limpa. Instância OLX isolada na porta 8766, com banco/perfil separados, para coexistir com trabalho na tela de cupons.

- Corrigida perda de confirmação de cupons quando o Mercado Livre navega ou fecha o modal após Inserir. Observa a resposta oficial do formulário `/cupons/api/input-code`, exclusivamente POST do código em `coupon_input_code`, e confirma somente mensagem de sucesso explícita; HTTP 200 sozinho não confirma. Leitura da tela continua como alternativa e tolera contexto temporariamente destruído, sem reenviar nem recarregar. Cinco regressões novas; 24 testes específicos e 386 gerais aprovados, compilação limpa. Revalidação real atualizou CARRINHOCHEIOJA de pendente para já existente; MELIGOODMOOD respondeu problema temporário e permaneceu pendente. Sem inserção nova comprovada na validação.

## 2026-10-05

- Aplicador reaproveita a página e o modal de cupons: só navega quando a aba está fora de `/cupons`, limpa o input antes de cada código e reabre o modal apenas se fechado. Feedback repetido exige nova alteração da resposta, sem atribuir o erro anterior ao código seguinte. Limpeza do observador não sobrescreve confirmação quando o site muda de página. 19 testes específicos e 381 gerais aprovados. Teste real de duas tentativas registrou uma única navegação iniciada pelo monitor; Mercado Livre retornou problema temporário e mudança de contexto por navegação do próprio site, preservados como pendências.

- Corrigida identificação da Ventoinha 2 (`ventoinha nordwind black`): ventoinha/fan/cooler para gabinete equivalentes em buscas personalizadas, mantendo modelo/cor e exclusão de kits/acessórios. Dois testes novos cobrem identificação, descoberta e leitura. 379 testes aprovados e compilação limpa. Duas ofertas reais Nordwind Black/Reverse Black da Terabyte salvas, ambas R$ 29,99 no Pix e aceitas no catálogo; cadastro preservado.

- Corrigida leitura dos erros de cupom: “Este cupom não se aplica a você” é recusado, preservando a mensagem exata e evitando nova tentativa. Feedback desconhecido permanece pendente com a resposta real; aviso genérico só quando não há resposta visível. Textos do modal e duplicatas removidos do detalhe. Três regressões novas cobrem classificação, captura e persistência/evitação de reaplicação.

- Aplicador de códigos do Mercado Livre: tarefa local horária, botão na aba Cupons e histórico persistente por código. Usa o perfil salvo e formulário oficial; identifica cupons exclusivamente da loja, deduplica códigos, preserva pendências e não repete inseridos/já existentes/recusados explícitos. Fonte pausada e login pendente respeitados; execução aguarda consultas. Confirma somente feedback novo visível; CAPTCHA/login continuam humanos. Corrigida abertura do modal antes da hidratação após falha observada no site real. 14 testes de regressão, 374 testes totais aprovados, compilação limpa. Teste real registrou recusa de cupom indisponível e respostas pendentes; não houve sucesso de inserção confirmado nessa validação. UI e botão verificados no painel local.

## 2026-10-03

- Terabyte Shop nas fontes, filtros, consultas globais/por peça e identificação de links/cupons. Busca pública `/busca?str=` e leitura isolada da área do produto: Pix explícito, total cartão, parcelas, vendedor e disponibilidade. Preço antigo, tabela de alternativas e relacionados descartados. Segue pausa, ciclo de dez minutos, marcas, corte de 12 e Mercado Livre por último; sem login ou novas dependências. Oito testes novos e ajustes das listas de lojas nos testes existentes; 360 testes aprovados e compilação limpa. Consulta real leu placa, NV3 1TB e water cooler; CX750 encontrada sem preço legível, sem confirmação inventada.

- Confirmação Shopee separada dos filtros da primeira peça: aceita produtos legíveis de outros modelos e testa busca ampla por SSD quando a página informa ausência de resultados. Espera títulos dos cards antes de ler; página vazia não confirma nem é tratada como erro de login. Filtros da coleta e perfil preservados. Cinco regressões novas, 352 testes aprovados e compilação sem erros. Teste real do perfil salvo ainda redirecionou para verificação de segurança; preços autenticados permanecem sem validação.

## 2026-10-02

- UX lotes 23–35: preço com cupom confirmado menor em destaque, preço original separado e foco preservado em atualizações de cartões/comparação, inclusive após remontar a aba. Consulta individual com resultado por loja; seleções/vazios próprios, ações contextualizadas e cancelamentos com retorno de foco. Abas fixas, paginação posicionando conteúdo e troca manual de área no topo; comparação recolhida alcançável durante rolagem. Cupons com contagem por loja, horários honestos, leitura estável durante atualização e identificadores por origem/código. Histórico contextualizado por pagamento, eixo BRL e descrição acessível em português; rascunho protegido antes da recarga. Limpar busca de fontes recupera foco no campo. 347 testes aprovados, compilação/detector limpos. Detalhes e limites da validação real/controlada em UX-ITERATIONS.md. Regras dos coletores, preços, corte e avisos preservadas.

- UX lotes 21–22: lista de peças como entrada, formulário sob demanda e cancelamento com foco; proteção de rascunho antes de trocar/descartar edição. Busca de fontes por nome, @grupo e ID, sessões recolhíveis com estado e atalhos das lojas direcionados. Cupons com Limpar filtros, nomes acessíveis por publicação, condições preservadas e link sem loja identificada rotulado honestamente. Tooltip de Ocultar substituído por descrição nativa para evitar âncoras removidas durante atualizações. Quatro regressões novas, 323 testes aprovados; compilação/detector limpos. Navegador confirmou recuperação de filtros, edição preservada e cancelada sem salvar, foco e paginação sem novos erros. Monitor ativo PID 16404.

- UX lote 20: filtros secundários recolhíveis, filtros ativos removíveis, seleção rápida do catálogo/favoritas/ocultas e cabeçalho compacto. Comparação recolhida com apenas diferenças, seleção visual e preservação de estado. Ocultação com Desfazer, nomes acessíveis, foco após recriar cartão e histórico abaixo da paginação. Corrigida abertura simultânea de peças ao trocar filtros. Oito testes novos (319 totais aprovados), compilação/detector limpos; interface real em 1280/1024px sem overflow. Regras de coleta e ranking preservadas.

- Item 5 do roadmap: favoritas persistentes, comparação inline de até três ofertas da mesma peça e ocultação/restauração de anúncios na aba Ofertas. Preferências seguem anúncios agrupados e sobrevivem à atualização e união de URLs; ocultos deixam consultas automáticas e alertas, preservando histórico. Catálogo conserva top 12; favoritas fora do corte ficam acessíveis sem forçar consultas. Pagamentos/cupom separados e frete desconhecido explícito.
- Validação: 12 regressões novas, 311 testes totais aprovados e compilação Python limpa. Interface real confirmou favorita após reload, seleção própria, comparação de três/recusa da quarta, ocultação persistida, restauração e retirada da comparação. Corrigido feedback emitido após recriar o cartão; log sem erros no processo final. Preferências temporárias revertidas. Evidência: `.impeccable/review/favorites-comparison.jpg`.

- Shopee adicionada à lista de lojas, consultas/filtros e identificação de links/encurtadores. Perfil próprio do Chrome com abrir/confirmar sessão em Fontes; login humano, isolamento dos demais perfis e diagnósticos de bloqueio. Leitura de preço estruturado em BRL, sem inferir Pix nem confirmar faixa de variações. Treze regressões novas, 297 testes aprovados; compilação/detector sem erros. UI real validada, coleta autenticada pendente do login humano.

- Após login humano Shopee, consulta real retornou Tente Novamente Mais Tarde sem produtos. Corrigida a mensagem que confundia esse bloqueio com falta de peças; perfil preservado e orientação para tentar confirmação depois. Regressão adicional, 298 testes aprovados; preços autenticados ainda não confirmados devido ao bloqueio.

- Diagnóstico também reconhece /verify/captcha antes do texto carregar; mensagem de bloqueio validada no botão real em Fontes. 299 testes aprovados. Coleta direta Shopee ainda depende de liberação da verificação pelo site.

- Corrigida consulta de water cooler: busca por 360 reconhece 360mm, preservando marca/ARGB e rejeitando outros tamanhos; links water-cooler da Pichau reconhecidos. KaBuM recebe a dimensão com unidade sem alterar o cadastro. Mercado Livre sem filtro Local pode descobrir candidatos, ainda exigindo origem nacional confirmada para catálogo/avisos e recusando redirecionamento que retire um filtro explícito. 284 testes aprovados e compilação sem erros.

- Atualizar peça na aba Ofertas: busca novas ofertas e confere preços somente do grupo escolhido nas lojas ativas, com estado de carregamento e identificação do componente consultado. Mantém corte de 12, marcas, envio nacional, Mercado Livre por último e filtros/paginação; não relê cupons gerais nem adia ciclos das outras peças. Oito regressões novas, total de 280 testes aprovados e compilação/detector sem erros.

- Limite confirmado de 12 ofertas por peça entre todas as lojas, após agrupamento e preço com cupom confirmado. Filtros e paginação atuam sobre essa seleção; empates não ultrapassam 12. Anúncios conhecidos acima do corte deixam consultas automáticas, inclusive fila e revalidação; primeira leitura de link sem preço e conferência manual preservadas. Registros/histórico mantidos e ofertas antigas baratas não são perdidas pelo antigo limite de 300 registros recentes.
- Validação final do limite: 14 regressões novas, total de 272 testes aprovados, compilação e detector sem achados. Catálogo real com cinco peças e 12 grupos por peça; páginas 1–6/7–12 conferidas, sem terceira página. Fonte pública e 90 observações reais com cupom preservadas no banco ao encerramento.

- Revalidação de ofertas com validade de 30/90 minutos; preços vencidos ou cuja conferência falhou saem das comparações, preservando registros/histórico. Até quatro anúncios antigos ausentes da busca são conferidos por peça/loja/ciclo.
- Cupom confirmado participa do aviso compatível e da referência de queda; histórico salva desconto por leitura e oferece Melhor preço, incluindo cupom, mantendo pagamentos originais. Migrações aditivas com backup; nenhuma reconstrução de descontos antigos.
- Cupons identificados por loja/link, incluindo destinos explícitos de afiliados, entidades Telegram, Shopee e AliExpress. Filtro por loja, fonte distinta, condições e links de uso/publicação. Fonte pública Melhores Cartões integrada com consulta a cada 30 minutos, cache limitado a 12 horas e entradas explicitamente inativas descartadas.
- Validação: 258 testes aprovados e compilação sem erros. Fonte real trouxe 106 cupons/ativações (98 Mercado Livre, oito Amazon); três leituras reais com cupom gravadas no histórico. Interface de cupons e filtro Amazon conferidos no navegador desktop.

- Mercado Livre restrito a envio local: busca segue o link Local publicado pelo site e recusa redirecionamentos que removem o filtro. Indicadores internacionais dos cartões e da área de compra/entrega do produto são conferidos. Ofertas internacionais ou ainda sem origem confirmada saem do catálogo, comparações e avisos, preservando registros; migração aditiva com backup. Onze regressões novas, total de 238 testes aprovados e compilação sem erros.

- Mercado Livre: preço explícito com cupom da sessão aparece separado no cartão/detalhes e participa da ordenação e escolha de anúncios agrupados. Preço anunciado sem Pix permanece separado do total parcelado; publicidade do cartão Mercado Pago não fornece preço do produto.
- Consultas automáticas: Pichau, KaBuM e Amazon mantêm intervalo de dez minutos; Mercado Livre fica por último e usa trinta minutos. Consulta manual antecipa a leitura; duração do ciclo é descontada da espera seguinte.
- Identificação de marcas e seleção pesquisável de Marcas ignoradas por peça; fabricantes excluídos saem da coleta, catálogo e avisos. Preferências persistem e registros antigos continuam preservados; nenhuma marca ignorada por padrão.
- Validação: 227 testes aprovados, compilação sem erros e detector visual sem achados. Cupom real do NV3 (R$ 836,92 → R$ 753,23), ordenação e exclusão/restauração de INNO3D conferidos no navegador real. Monitor reiniciado com as alterações.

- Mercado Livre: confirmação e coleta tentam o mesmo perfil do Chrome com janela após um 403 sem janela. Modo aceito é salvo para os próximos ciclos e reinícios; uma aba permanece aberta para não encerrar o navegador entre consultas. Login, verificação humana, limite de consultas e bloqueio recebem diagnósticos distintos.
- Validação dessa correção: 199 testes aprovados e compilação sem erros. Busca real retornou 12 links RTX 5060, um produto foi lido por R$ 2.899,03 sem condição de pagamento explícita e outra busca consecutiva passou. Após reinício, o ciclo automático gravou ofertas do Mercado Livre no banco local.

- Identificação exclui acessórios, kits e capacidades misturadas; estojo NV3 antigo deixa de participar do catálogo, histórico e ranking, sem apagar seu registro.
- Histórico por peça com menor preço, mediana diária e gráfico em 7/30 dias, pagamentos separados e indicação de poucos dados. Consultas com preço constante registram um novo dia observado. Novas leituras preservam estoque e excluem preços esgotados; estoque antigo fica desconhecido.
- Avisos Windows explicam a classificação e a comparação histórica quando há dados suficientes. Repetição exige queda de pelo menos 2% no mesmo pagamento, mantendo teto/top 10%; cupons e pequenas oscilações não geram novos avisos. Confirmação esclarecendo pagamento estabelece referência silenciosa.
- Migração aditiva preserva avisos e referências, inclusive ao reunir URLs. Envio concorrente não duplica avisos e falha de envio não muda o preço de referência. Backup local anterior à migração preservado em data/backups.
- 188 testes aprovados; compilação Python e detector visual sem achados. Validação final no navegador documentada em CHECKPOINT.md.

- Avisos restritos aos 10% mais baratos de cada peça/pagamento, com arredondamento para cima e empates no corte. Mantidos teto individual, atualidade, pausa e prevenção de repetição; ofertas fora da faixa continuam salvas. Anúncios agrupados/indisponíveis/sem preço positivo não inflam a faixa.
- Conferência pode avisar quando o preço passa a ser conhecido e atrativo, mesmo sem teto; aviso com limite no cartão mostra o total comparado. Textos do painel explicam a regra.
- Validação: 159 testes aprovados, incluindo doze regressões de classificação, Telegram, consulta de lojas, conferência e conteúdo do aviso; compilação Python sem erros.

## 2026-10-01

- Filtros de peça, loja e conferência no catálogo, combinados com busca e limpeza; cabeçalhos com menor valor disponível e limite, horários nos cartões e indicadores de loja acionáveis. Consulta em andamento desabilita nova consulta; filtros atualizam por evento.
- Contexto de vendedor/anúncios agrupados no cartão; retorno de foco após conferir detalhes e foco no campo inválido dos formulários. Linhas de peças/fontes e cartões identificados na navegação assistida. Indicador Mercado Livre orienta fechar Chrome e confirmar quando a sessão está pendente.
- Resumo visual NV3 separa capacidade/interface e mantém Mini/2230/2280, sem inferir dados de SKU ou transformar kits/acessórios em SSDs; título original permanece no detalhe.
- Cadastro/edição de peças com grade desktop, capacidade condicional, cancelamento explícito e mensagens por campo; valores negativos/mistos e capacidade inválida recusados antes de salvar. Lista exibe busca configurada.
- Fontes separadas entre Telegram e lojas; cadastro recolhível, seleção pesquisável de novos grupos, feedback de carregamento e salvamento, erros por campo e confirmação de remoção. Passos e estados da sessão Mercado Livre próximos aos controles.
- Detalhes com resumo de preços, mensagem/links/histórico recolhíveis e rodapé acessível; diálogo permanece aberto durante atualizações de cartões. Histórico inclui valor anunciado e conferência informa estado de fila.
- Cupons em lista compacta, com busca, condições recolhíveis, códigos selecionáveis e cópia confirmada pelo navegador; descontos permanecem não validados.
- Telegram mostra conexão, fontes e atividade, com ajuda de login recolhível e avisos em seção própria; teste de aviso mostra carregamento. Abas sem animação e busca de ofertas sem grupos vazios.
- Catálogo mostra início e conclusão dos ciclos de consulta, sem considerar um ciclo interrompido como concluído.
- Idade do preço/anúncio atualizada nos cartões sem reiniciar paginação. Detalhe acompanha resultado de conferência e histórico, mantendo expansões e encerrando seu timer ao fechar.
- Filtros de modelo explicam suas exclusões; seleção de grupos remove fontes recém-cadastradas das opções em cache. Resumo GPU separa memória/GDDR de códigos de fabricante e preserva variantes em títulos longos.
- Mercado Livre com janela de login e perfil persistente próprio do Chrome, controlados pela aba Fontes; confirmação por busca legível e consultas em segundo plano. Login em andamento pausa consultas; expiração e bloqueios humanos ficam explícitos. Playwright passou a dependência de execução. Validação autenticada real pendente do login do usuário.
- Cartões repetidos do mesmo modelo e vendedor na mesma loja agrupados, incluindo URLs com/sem -NAC da Pichau; variantes preservadas e anúncios/histórico mantidos em Detalhes.
- KaBuM e Amazon adicionadas às consultas diretas e à conferência de links; suporte a amzn.to. Busca e preços reais coletados nas duas lojas; falhas de consulta permanecem visíveis. URLs Amazon normalizadas por ASIN, mantendo parâmetros de vendedor e histórico existente.
- Tabela de ofertas substituída por cartões responsivos, com modelo resumido, preço em destaque, loja e link para o anúncio; nome completo, horários, histórico e conferência em Detalhes.
- Seis cartões por página e diagnósticos longos recolhidos em Estado das fontes. Pix, total no cartão e pagamento desconhecido continuam distintos; cupons não implicam desconto validado.
- Ofertas sempre ordenadas pelo menor preço mostrado dentro de cada peça, antes da paginação; preços desconhecidos ficam no final.
- Ofertas agrupadas pela peça acompanhada, com seções recolhíveis e paginação própria.
- Explicação no painel sobre recepção de mensagens novas do Telegram e cupons gerais.
- Correção do falso erro de acesso ao cadastrar o mesmo canal por nome e ID; estados das fontes atualizam no painel.
- Login local com diagnóstico específico por etapa, sem imprimir credenciais.
- Login do Mercado Livre ajustado para Chrome normal, sem automação, após captcha ausente e consulta recusada com 403 na primeira tentativa. Usuário fecha a janela antes de confirmar; nenhum captcha é resolvido automaticamente. Autenticação e coleta real seguem pendentes.
- Validação automatizada: 147 testes aprovados.
# 2026-10-07 — painel cloud e ponte local

- Painel/API FastAPI para Vercel, Supabase Auth e persistência isolada por conta/RLS. Catálogo por peça, teto, 12 ofertas, preferências/comparação, cadastros, fontes, histórico, cupons e OLX.
- Consultas HTTP por peça e cupons públicos na nuvem. Fila persistente para Chrome/Telegram/OLX/aplicação de cupons no PC; agendamento cloud adiado.
- Conexão local com DPAPI, renovação de sessão e exportação incremental de campos permitidos, sem enviar arquivos/sessões/credenciais. Sincronização preserva leituras cloud mais recentes, estados e histórico.
- Dependências cloud separadas; arquivos privados excluídos do deploy e Git. 26 regressões novas, 487 testes gerais aprovados, RLS real e interface isolada validados.

### UX — foco das listas e acesso concorrente
- Cupons em páginas de 12, recentes primeiro; outras lojas não mostram aplicação Mercado Livre nem herdam seu filtro de estado.
- Atividade separa pendências do histórico paginado; consultas da fila preservam pedidos antigos pendentes além dos últimos 50 finalizados.
- Renovação de sessão compartilhada entre consultas concorrentes.
- Região Vercel gru1 confirmada em produção; KaBuM continua retornando leituras, Pichau/Terabyte seguem com HTTP 403.

### UX — cartões, grupos e recuperação de cupons
- Preços alinhados em cada linha de cartões; nomes completos do vendedor continuam acessíveis.
- Referências técnicas e exclusão dos grupos recolhidas; alteração pendente impede envio repetido.
- Fontes públicas de cupons consultadas independentemente na nuvem, com timeout/cooldown e último resultado preservado por fonte. Códigos sincronizados para o aplicador sem reaplicar ativados.
- Ao pedir o próximo lote, o PC encerra pedidos em execução sem confirmação há mais de uma hora, sem reenvio automático.

### UX — edição e informação contextual
- Marcas pesquisáveis, contagem e remoção visível da seleção. Formulário isolado da lista durante edição.
- Erros de campo com mensagem associada, destaque e foco, sem perder os valores.
- Peças mostram teto e condição; busca, fabricantes e exclusão ficam em expansão. Listas vazias explicam filtros/teto e oferecem ação adequada.
- Favoritas ordenadas pelo preço que o cartão realmente mostra; comparação avisa quando o cupom não tem confirmação atual.

### Histórico cloud
Consulta as leituras da peça e do período diretamente no Supabase, mantendo RLS e os cálculos de preço. Limite considera as leituras mais recentes e informa truncamento; não apaga histórico.

### Comparação e conexão
- Seleção de até três ofertas fica acessível em barra discreta; tabela de pagamentos, cupons e conferência abre em diálogo, com links de compra e foco devolvido ao fechar.
- Requisições têm prazo adequado ao tipo de consulta, erro de conexão em português e mensagem de resultado incerto para operações sem resposta. Sessão expirada fecha os diálogos e permite entrar novamente.

### 08/10/2026 — descoberta horária de cupons públicos
- Coleta na nuvem compartilhada pelo botão e pelo Supabase Cron; fontes independentes e cache por conta.
- Agendamento privado reaproveita Vault, evita lotes duplicados e não sobrescreve uma leitura manual posterior.
- Painel informa a execução automática sem misturar descoberta com ativação no Chrome.

### 08/10/2026 — catálogo compacto e presença do PC
- Cartões com título resumido, menor altura e preços alinhados; título completo nos detalhes.
- Configuração dos grupos Telegram recolhida com contagem e estado da coleta.
- Presença do PC expira pelo relógio sem depender de uma resposta nova; controles de sessão seguem o mesmo estado.

### 08/10/2026 — favoritas sem recarregar o catálogo
- Estrela atualiza imediatamente e bloqueia cliques repetidos enquanto salva.
- Falhas restauram o estado e consultam a confirmação da nuvem, inclusive em anúncios agrupados.
- Validação com resposta de API lenta, falha parcial e sessão expirada.

### 08/10/2026 — histórico e estados acessíveis
- Consulta do histórico mostra carregamento e ignora respostas antigas após mudar a condição.
- Falha oferece retentativa e remove o gráfico da seleção anterior.
- Listas anunciam contagens sem reler todos os cartões a cada atualização.

### 08/10/2026 — pedidos com contexto
- Atividade identifica a peça, anúncio, grupo, busca ou cupom de cada pedido.
- Nome do registro é preservado no pedido; nomes de registros existentes vêm da própria conta.
- Registros anteriores usam o contexto disponível, sem inventar nomes.

### 08/10/2026 — preferências independentes no banco
- Favoritar e ocultar alteram somente o próprio campo em uma gravação atômica.
- Evita que ações próximas apaguem a preferência anterior e elimina leituras intermediárias da API.
- RPC restrita à conta autenticada e à oferta existente.

### 08/10/2026 — Usados na OLX
- Anúncios do menor para o maior preço, seis por página, respeitando cidade, teto e palavras excluídas.
- Preço anunciado e presença antiga separados; datas, resultado e configuração sob demanda.
- Pedidos na fila bloqueiam reenvio; cadastro é validado na nuvem antes de chegar ao PC, com erro junto ao formulário.
- Termos separados por linha viram exclusões independentes; UF escolhida em lista.

### 08/10/2026 — validade do preço mesmo sem rede
- Mais baratas remove leituras vencidas pelo relógio, sem esperar nova resposta do servidor.
- Favoritas preserva o último valor e mostra que precisa conferir; cupom vencido deixa de ser o preço atual.
- Detalhes atualizam a condição preservando foco e seções abertas da mesma oferta.

### 08/10/2026 — validação de grupos junto ao formulário
- Normalização de referência compartilhada entre API e cadastro local.
- Formato e duplicação são verificados antes do pedido ao PC, inclusive grupos ainda na fila.
- Erro preserva o rascunho; cadastro correto fecha o formulário e segue para Atividade.

### Atualizações que preservam a interação
- Fontes e OLX mantêm os detalhes abertos e o foco; respostas antigas não substituem consultas recentes.
- A atualização automática aguarda formulários, diálogos e operações em andamento e não cria consultas concorrentes.

### Sessão e preços salvos
- Sair da conta invalida leituras pendentes de catálogo/cupons e limpa a seleção/paginação.
- Ordenação das ofertas salvas acompanha o preço mostrado, desconsiderando cupom vencido.
