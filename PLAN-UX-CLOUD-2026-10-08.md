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

Rodada 3: 51 testes cloud, duas suítes JS e Chrome/ASGI aprovados. Cupons paginados, filtros por loja sem ações impróprias, fila antiga preservada e renovação única de sessão. Capturas reais em 1440/1024 sem erro JS/overflow. /health confirma gru1; a mudança de região não resolveu o 403 de Pichau/Terabyte, KaBuM continua com leituras.

## Rodada 4 — recuperação e cupons públicos
Cartões alinhados e grupos com configuração recolhida. Busca pública com fontes/timeout independentes, cache exclusivo da nuvem e importação pela ponte para o aplicador; sem nova infraestrutura. Pedidos antigos em execução não podem bloquear lotes futuros indefinidamente; encerramento quando o PC pede o próximo lote, sem reenvio. Suíte completa de 523 testes aprovada antes da proteção final da fila; executar a regressão específica e validar publicação/ponte.

Rodada 4 publicada em 9fff1d0: produção confirmou 66 cupons não ML apesar das outras duas fontes com 403; ponte reiniciada com /health 200/running; pedidos em execução desde ontem encerrados sem reenvio.

## Rodada 5 — edição e critérios
Busca e remoção de marcas, campos inválidos com foco/mensagem acessível, critério de preço explícito e lista recolhida durante edição. Favoritas usam valor exibido e comparação identifica cupom antigo. Duas suítes JS e Chrome/ASGI aprovados; captura de formulário real sem erros JS/overflow. Apenas front end nesta rodada.

## Rodada 6 — histórico sem baixar todas as peças
RPC read-only `monitor_recent_observations` com SECURITY INVOKER, auth.uid(), RLS e execução anônima revogada. Consulta somente a peça/período, limitada a 10 mil leituras recentes com indicação de leitura parcial. Migração aplicada pelo plugin; teste SQL com 10.001 leituras, outra peça, data antiga e duas contas passou e foi revertido (0 fixtures restantes). EXPLAIN em dados reais: 13,685 ms, sem novo índice. 56 testes cloud e Chrome/ASGI aprovados. Comparar os pontos após publicar.

Rodada 6 publicada em 633bdce: os históricos das três peças preservaram exatamente os mesmos pontos/valores; mediana de três consultas /history/5 caiu de 4,472 s para 1,755 s (medição pontual, sem promessa de SLA). Sete páginas reais da produção verificadas no Chrome: sem erro JS, HTTP ou overflow.

## Rodada 7 — comparação e conexão
Barra de comparação com progresso e diálogo sob demanda; leitura e links de cada oferta explícitos. Timeout por tipo de operação e erro de rede legível, distinguindo resultado incerto; expiração da sessão fecha diálogos. Testes JS de timeout/rede e Chrome/ASGI de seleção, foco, fechamento e sessão expirada aprovados; captura real da comparação sem erro/overflow.

## Rodada 8 — descoberta periódica de cupons na nuvem
Compartilhar a coleta pública entre botão e endpoint agendado; Supabase Cron/pg_net usa o Vault existente a cada hora, sem Vercel Cron nem JWT administrativo. Cache privado por conta, cooldown compartilhado com o botão, fontes independentes e resposta antiga não sobrescreve atualização manual. Ativação ML permanece no PC. Validar API, função SQL com fixtures revertidas, deploy e execução real antes de habilitar o cron.

Rodada 8: 529 testes Python, dois testes JS e Chrome/ASGI aprovados. Migração aplicada pelo plugin Supabase; fixture SQL real confirmou cache, conta, timeout, atomicidade, leitura manual e cooldown, com 0 usuários de teste restantes. Habilitar e verificar coleta real após o deploy.

## Rodada 9 — densidade e presença do coletor
Reduzir espaços do catálogo preservando alinhamento dos preços, resumo do modelo em duas linhas com título completo nos detalhes; recolher grupos Telegram e mostrar contagem/estado. Atualizar a indicação de PC pelo relógio, mesmo sem resposta nova. Validar JS, Chrome/ASGI e capturas reais desktop.

Rodada 8 publicada em 5bd987b. Endpoint real rejeitou chamada sem segredo (401). Cron Supabase habilitado e execução real salvou 67 cupons de outras lojas; Pelando/Pichau 403 registrados sem cancelar MC. Ativação ML não mudou.
Rodada 9: JS e Chrome/ASGI aprovados, capturas com dados reais em 1440/1024 sem erro/overflow; Fontes agora cabe em uma tela com os nove grupos recolhidos.

## Rodada 10 — favoritas com retorno imediato
Estrela muda no clique e bloqueia reenvio enquanto salva todos os anúncios agrupados; sucesso não recarrega o catálogo. Em erro, restaura a indicação e consulta o estado confirmado para resolver falha parcial. Preservar foco e testar resposta lenta, erro/reversão e sessão expirada.

Rodada 10: teste JS de resposta lenta, reenvio, reversão por anúncio agrupado e expiração de sessão aprovado. Chrome/ASGI confirmou estrela imediata com API bloqueada e ausência de recarga do catálogo após salvar.

## Rodada 11 — consultas e anúncios de estado
Histórico mostra consulta em andamento, preserva apenas a resposta mais recente e oferece retentativa no próprio painel quando falha; nenhum gráfico antigo continua sob um filtro novo após erro. Listas não anunciam todo o conteúdo a cada atualização: comunicar contagens/estados separados. Validar concorrência, erro, retentativa e Chrome.

Rodada 11: teste JS de respostas fora de ordem, falha, retentativa e vazio aprovado. Chrome/ASGI confirmou aria-busy/carregamento com API bloqueada. Produção anterior: sete páginas sem erro JS/HTTP/overflow.

## Rodada 12 — contexto dos pedidos
Pedidos do PC identificam peça, anúncio, grupo, busca ou código de cupom. Rótulos de registros existentes vêm da própria conta no servidor e sobrevivem à exclusão; registros antigos usam contexto disponível ou identificação explícita, sem inventar nomes. Validar contrato do worker, propriedade e escaping na interface.

Rodada 12: 62 testes cloud, JS de contexto/escaping e Chrome/ASGI aprovados; worker continua usando os mesmos campos, apenas ignora o rótulo adicional.

## Rodada 13 — preferências independentes
Favoritar/ocultar usa uma gravação atômica de um único campo no Supabase; ON CONFLICT mescla o estado atual, evitando read-modify-write na API. RPC invoker, RLS, propriedade da oferta e lista explícita de campos. Validar SQL com duas contas, preservação de campos, oferta ausente e API/UI.

Rodada 13: migração aplicada pelo plugin. SQL real validou preservação de campos, alterações isoladas entre duas contas, oferta ausente e rejeição de campo arbitrário; fixtures revertidas. 64 testes cloud, favoritos/histórico JS e Chrome/ASGI aprovados.

Correção de contrato: source_save/olx_save usam o nome já presente no payload; não acrescentar label a olx_save, que passa kwargs ao parser local. Teste executa o parser real com o payload que a API enfileira.

## Rodada 14 — Usados com critérios e presença honestos
Reutilizar a regra OLX de elegibilidade sem instanciar coletor/navegador; API marca elegibilidade e ignora registros sem busca correspondente. Cartões ordenados por preço, seis por página; separar preço anunciado de presença confirmada, datas/configuração sob demanda e bloquear pedido repetido na fila. Validar API com cidade/teto/exclusões, UI com dados sintéticos identificados e estado vazio real.

Rodada 14: 67 testes cloud aprovados. UI JS protege elegibilidade/preço/paginação/antiguidade/fila. Chrome/ASGI validou seis cartões, foco na troca de página, consulta sem reenvio e formulário inválido que preserva os campos; cadastro correto normaliza exclusões por linha. Captura OLX usa fixtures explicitamente sintéticas; produção ainda sem buscas sincronizadas, sem alegar coleta real.

## Rodada 15 — validade visual independente da rede
Reavaliar preços quando o relógio cruza valid_until, sem esperar resposta HTTP. Mais baratas remove leituras vencidas; favoritas/ocultas mantêm o último valor com aviso. Se os detalhes estiverem abertos, atualizar condição preservando foco e disclosures. Comparação usa o preço com cupom só enquanto válido. Validar clock e detalhes no Chrome.

Rodada 15: quatro testes JS e Chrome/ASGI aprovados. Teste de relógio protege catálogo e preço salvo; Chrome verifica atualização dos detalhes com foco preservado.

## Rodada 16 — grupos validados antes da fila
Compartilhar a normalização já usada pelo cadastro local, sem banco ou acesso ao Telegram na nuvem. API valida formato e duplicação (inclusive pedido pendente); formulário preserva rascunho e explica erro junto aos campos. Confirmação da conta/participação continua local e não há entrada automática em grupos.

Rodada 16: 68 testes cloud e 50 testes core aprovados; JS e Chrome/ASGI confirmaram erro no formulário sem perder rascunho, normalização e bloqueio de duplicação pendente.

## Rodada 17 — atualização sem interromper a interação
Preservar foco e detalhes nas listas de Fontes/OLX; ler disclosures após a resposta, não antes. Ignorar respostas antigas de Fontes/OLX. Atualização automática não sobrepõe edição, diálogo, operação ativa ou outra atualização; segue a aba que iniciou a consulta. Validar concorrência, rascunho, foco e disclosures no Chrome.

Rodada 17: teste JS de respostas fora de ordem e atualização concorrente aprovado; Chrome/ASGI abriu uma sessão durante resposta lenta e preservou disclosure/foco, além das datas abertas de anúncio OLX. Atualização automática pausa durante formulário, diálogo ou operação ativa.

## Rodada 18 — sessão e ordenação coerentes
Invalidar respostas de catálogo/cupons ao sair ou trocar de sessão; limpar seleção e paginação da conta. Ordenar ofertas salvas pelo valor efetivamente exibido, sem depender de preço auxiliar que possa conter cupom antigo. Validar respostas atrasadas e cupom vencido em JS e regressões Chrome.

Rodada 18: cinco suítes JS e Chrome/ASGI aprovados. Teste de saída/troca de sessão confirmou que respostas atrasadas não repõem catálogo/cupons; ordenação usa o preço mostrado. Produção da rodada 17: sete páginas sem erros JS/HTTP/overflow.

## Rodada 19 — resultado público conciso
Resumo de coleta com quantidade realmente consultada e fontes indisponíveis; falhas completas permanecem no disclosure existente. Nenhuma fonte respondeu não vira sucesso ou ausência de cupons. Validar sucesso, falha parcial e falha total em JS/Chrome.

Rodada 19: JS e Chrome/ASGI aprovados; falha parcial mostra contagem sem apagar o motivo e falha total informa preservação do dia.

## Rodada 20 — foco nas listas restantes
Aplicar a proteção de foco existente aos detalhes de cupons e ações de Atividade; atualizar informações sem tirar a navegação do teclado. Validar disclosures de cupom e cancelar pedido com recarga no Chrome.

Rodada 20: Chrome/ASGI confirmou foco no summary de cupom e no botão de cancelar pedido após recarga; detalhes permanecem abertos. JS geral/concorrência aprovados.

## Rodada 21 — leitura de cupons sem ida sequencial adicional
Ler os estados junto dos quatro conjuntos que a API já busca em paralelo. Sem alteração de dados, autenticação ou contrato; os testes existentes de estados/filtros/falhas/agendamento e Chrome são a validação relevante, sem teste que apenas repita asyncio.gather.

Rodada 21: 68 testes cloud e Chrome/ASGI aprovados; payload e estados preservados.
