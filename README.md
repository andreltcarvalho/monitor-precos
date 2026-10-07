# Monitor de peças

Aplicativo local para acompanhar RTX 5060 de fabricantes variados, Corsair CX750 e Kingston NV3 1 TB. Permite cadastrar outras peças, selecionar grupos e configurar limite por Pix ou total parcelado.

Os avisos só são enviados para ofertas entre os **10% mais baratos da mesma peça**, comparando o mesmo pagamento. O limite individual continua sendo uma condição adicional. Com até dez anúncios comparáveis, só o menor preço qualifica; com vinte, os dois menores. Empates no preço de corte qualificam. Anúncios indisponíveis, sem preço positivo e repetições agrupadas não aumentam a amostra. Os demais anúncios dentro do limite de preço continuam no painel sem gerar aviso.

## Abrir

Nesta máquina, as dependências já estão instaladas. Abra `Iniciar-Monitor.cmd` e acesse http://127.0.0.1:8765. Fechar a aba mantém o monitor ativo; use **Encerrar** para parar.

## Painel na Vercel e coletor no PC

O painel da nuvem usa FastAPI por requisição e Supabase Auth/Data API, com dados isolados por conta por RLS. Não depende do SQLite ou do Chrome no servidor. O painel local continua disponível normalmente.

No [painel publicado](https://monitor-precos-snowy.vercel.app), crie sua conta, confirme o e-mail e entre. Depois execute `Conectar-Nuvem.cmd` na pasta do monitor, informe `https://monitor-precos-snowy.vercel.app` e o login dessa conta, e reinicie o monitor local. A senha não é salva: os tokens de sessão/renovação ficam em `data/cloud-credentials.bin`, protegidos pelo Windows/DPAPI. Não copie esse arquivo para outro computador.

O PC sincroniza a cada minuto cadastros, ofertas, leituras históricas, fontes, cupons e buscas da OLX. A exportação usa uma lista explícita de campos; arquivos, cookies, perfis do Chrome, telefone e credenciais do Telegram não são enviados. Após conectar, faça as alterações de peças, fontes e preferências pelo painel da nuvem; essas alterações são aplicadas ao monitor local.

**Buscar ofertas desta peça** consulta Pichau, KaBuM, Amazon e Terabyte na Vercel, nas fontes ativas. Essas consultas usam os parsers existentes, têm duração limitada e um intervalo mínimo de cinco minutos por peça. Bloqueios preservam o histórico e aparecem no resultado da consulta. Mercado Livre e Shopee recebem um pedido na fila para consulta no PC; o Mercado Livre permanece por último nessa consulta local. OLX, recebimento do Telegram e aplicação de cupons também permanecem no PC, com suas sessões atuais. Pedidos feitos com o PC desconectado aguardam na aba **Atividade**.

O catálogo mantém o limite de 12 por peça, agrupamento, ordenação pelo preço com cupom e limite de pagamento cadastrado. O histórico da nuvem considera até 10.000 leituras por consulta e sinaliza quando fica parcial. **Cupons** mostra os códigos de hoje, estados e motivos/retentativas, e permite consultar as fontes públicas pela nuvem; ativação do Mercado Livre é executada no PC.

As consultas online também rodam automaticamente, mesmo com o PC desligado: **Supabase Cron → API da Vercel → histórico no Supabase**. O Cron verifica a fila a cada minuto, inicia até duas consultas de peça/loja por rodada e respeita dez minutos entre buscas do mesmo par. Com muitas peças, o intervalo efetivo pode aumentar. Peças/fontes pausadas ou excluídas são ignoradas, assim como peças com consulta manual iniciada nos últimos cinco minutos. Cada consulta dura no máximo dois minutos; erros/timeout encerram o lote e preservam os dados anteriores. Não usa Vercel Cron ou um processo contínuo no servidor. Os ciclos de Chrome, Telegram, OLX e ativação de cupons permanecem locais.

Para outro deploy, configure `SUPABASE_URL` e `SUPABASE_PUBLISHABLE_KEY` nos ambientes Preview/Production da Vercel. O entrypoint está em `pyproject.toml`, `cloud.app:app`; as dependências cloud também estão nesse arquivo. `cloud/schema.sql` contém o esquema aplicado ao Supabase. Não use chave administrativa no frontend ou no coletor. `.vercelignore` e `.gitignore` excluem bancos, sessões, arquivos de ambiente e dados locais.

Para habilitar o agendamento em outro projeto, aplique também `cloud/schedule.sql`. Gere um segredo aleatório exclusivo e configure-o como `MONITOR_CRON_SECRET` na Vercel e `monitor_cloud_cron_secret` no Vault Supabase. No Vault, `monitor_cloud_cron_url` deve conter a URL completa de `/api/scheduled/collect` em produção. Somente depois do deploy validado, habilite o job `monitor-precos-cloud-searches` com o comando no final do SQL. O endpoint devolve leituras e não recebe uma chave administrativa do banco; o Supabase atribui o proprietário a partir do lote. Mantenha os esquemas internos `net`, `vault` e `monitor_private` fora da Data API. `public.monitor_scheduled_jobs` registra o resultado de cada peça/loja e permite apenas leitura da própria conta; `cron.job_run_details` registra a execução do agendador. `tests/cloud_schedule.sql` valida a integração em uma transação revertida, sem enviar requisições.

As ofertas ficam agrupadas por peça em seções recolhíveis, com **até 12 ofertas mais baratas por peça**, somando todas as lojas e agrupando duplicados, em duas páginas de seis cartões. O teto da peça é aplicado antes do corte, e o corte acontece antes dos filtros de texto, loja e conferência; filtrar uma loja não traz anúncios acima dele. Cada cartão destaca modelo, loja, preço Pix quando informado, parcelamento e **Ver oferta**. **Detalhes** reúne nome completo, vendedor, horários, histórico e conferência do preço. **Estado das fontes** mostra os diagnósticos completos.

Anúncios conhecidos acima do 12º preço deixam de ser consultados automaticamente, sem apagar registros/histórico. Uma nova publicação com preço menor pode entrar; um link novo sem preço exige uma primeira leitura para decidir. Revalidação dos selecionados usa o último preço base conhecido quando a leitura vence, sem reutilizar cupom vencido. Conferência manual continua disponível. Ofertas esgotadas e marcas ignoradas não ocupam as 12 posições.

Nos cartões, **Salvar** guarda uma favorita no banco local. Em **Seleção**, escolha **Favoritas salvas** para ver até 12 favoritas por peça, inclusive fora do catálogo ou indisponíveis; salvar não força consultas acima do corte. **Comparar** seleciona até três ofertas da mesma peça para comparação lado a lado de pagamentos, parcelamento, cupom, vendedor e validade. Frete permanece **Não consultado**. A comparação vale para a aba aberta; favoritas continuam salvas após reiniciar.

**Ocultar** retira os anúncios atualmente agrupados naquele cartão do catálogo, consultas automáticas e alertas, mantendo histórico e favorita. Use **Seleção → Ofertas ocultas → Restaurar** para voltar a acompanhar. A ação preserva anúncios de outras lojas e variantes; a seleção de ocultas mostra até 12 por peça.

Para atualizar uma peça, expanda seu grupo em **Ofertas** e clique em **Atualizar peça**. A consulta busca novas ofertas e confere preços somente desse componente nas lojas ativas, respeitando o corte das 12 e mantendo o Mercado Livre por último. O status identifica a peça consultada; filtros e paginação ficam preservados. Durante outra consulta, os botões ficam indisponíveis. Essa ação não relê cupons gerais nem adia os ciclos automáticos das outras peças. Uma peça pausada precisa ser reativada para atualizar.

Dentro de cada grupo, as ofertas aparecem do menor para o maior preço: Pix quando disponível, senão total no cartão, senão valor anunciado com pagamento desconhecido. No Mercado Livre sem Pix, o preço principal é o valor anunciado; o total parcelado aparece separado. O preço explícito **com cupom na sua sessão** também entra na ordenação, usando o menor valor, e aparece separado no cartão e nos detalhes. Descontos percentuais e cupons sem preço explícito não são calculados. Anúncios sem preço ficam no final. O uso principal é no navegador do PC.

Em **Mais baratas**, o preço máximo da peça também filtra a exibição: valor até o limite, inclusive, no Pix ou no total no cartão conforme cadastrado. O filtro é aplicado antes do agrupamento e do corte das 12. Salvar outro limite em **Peças** atualiza a lista com os preços já registrados, sem nova consulta; apagar o limite volta a mostrar o catálogo sem teto. Sem preço conhecido no pagamento escolhido, a oferta não passa pelo limite; um preço com cupom de pagamento não identificado não é tratado como Pix/cartão. Favoritas e Ocultas continuam acessíveis em suas seleções, preservando ofertas e histórico.

Em **Peças → Editar → Marcas ignoradas**, selecione fabricantes para excluir daquela peça no catálogo, na coleta e nos avisos. A marca é reconhecida pelo título e por nomes conhecidos; identificação desconhecida ou ambígua continua visível. Remover a seleção restaura os anúncios já salvos, sem apagar registros ou histórico. Nenhuma marca é ignorada por padrão.

Abra **Histórico de preços** dentro da peça para consultar menor preço e mediana dos menores preços diários em 7/30 dias. Selecione Pix, total no cartão, pagamento não informado ou **Melhor preço, incluindo cupom**. Esta última opção usa o desconto confirmado de cada leitura e compara condições diferentes de pagamento; as demais preservam preços sem cupom. Dias sem dados e descontos antigos desconhecidos não são preenchidos. Menos de três dias aparece como histórico curto. Estatísticas não incluem frete, códigos sem preço validado ou filtros do catálogo.

Preços conferidos valem por 30 minutos nas demais lojas e 90 minutos no Mercado Livre; anúncios não conferidos do Telegram valem cinco minutos. Preço vencido ou consulta que falhou fica fora das comparações e aparece no fim com indicação de desatualização. O histórico passado permanece preservado. Cada ciclo também tenta conferir até quatro anúncios vencidos por peça/loja que não apareceram na busca.

Em **Cupons**, a loja aparece separada da fonte de publicação, com filtro por loja, condições, código copiável e links de uso/origem. Links conhecidos e destinos explícitos de afiliados identificam Pichau, Mercado Livre, KaBuM, Amazon, Shopee, Terabyte Shop e AliExpress; links ambíguos permanecem sem identificação. A página pública [Melhores Cartões](https://www.melhorescartoes.com.br/cupom-desconto.html) é consultada a cada 30 minutos antes do Mercado Livre, além do Telegram e da Pichau oficial. Uma falha conserva a última consulta por até 12 horas no painel. Cupons publicados não são aplicados automaticamente no checkout nem tratados como desconto confirmado.

Avisos explicam por que a oferta qualificou. A mesma oferta/modelo na mesma loja e vendedor só avisa novamente após queda de pelo menos **2%** desde o último aviso no mesmo pagamento, além de continuar entre os 10% mais baratos e respeitar seu limite. Cupom novo sem desconto confirmado não basta. O preço explícito com cupom da sessão participa dos avisos no pagamento não informado; não satisfaz um limite exclusivo Pix/cartão sem essa condição confirmada. Se a confirmação esclarecer o pagamento do anúncio, ela estabelece a referência sem outro aviso.

A seleção rejeita acessórios, kits e capacidades incompatíveis. Registros antigos incompatíveis ficam preservados no banco e saem das comparações normais.

Anúncios com o mesmo título completo e vendedor na mesma loja ficam em um cartão; na Pichau, o sufixo final `-NAC` não cria outro modelo. Variantes como White/V2, vendedores e lojas diferentes continuam separados. O cartão usa o menor preço disponível; links originais e histórico continuam em **Detalhes**, sem excluir registros salvos.

Em uma instalação nova, use Python 3.12 e execute `Instalar.cmd` antes de iniciar.

## Acompanhar usados na OLX

Em **Usados → Adicionar busca**, cole o link de uma busca da OLX com os filtros desejados, ou escolha **Produto e cidade** e informe produto, UF e cidade. Nome obrigatório; preço máximo e termos a excluir do título são opcionais. O link mantém os filtros da OLX e passa a ordenar pelos anúncios mais recentes.

Para **Piracicaba/SP**, o cadastro por produto usa diretamente a rota municipal verificada `/estado-sp/grande-campinas/piracicaba`, inclusive nas buscas já cadastradas. Não depende do seletor de localização da OLX, que pode estar indisponível. A coleta confirma a cidade no título da busca e descarta recomendações de outros municípios; uma página do estado inteiro não confirma uma busca local. As demais cidades continuam usando o seletor oficial ou o link de busca já localizado.

Cada busca consulta até 50 anúncios recentes a cada dez minutos. **Consultar agora** antecipa a leitura. A primeira consulta estabelece referência sem avisar o acervo; consultas seguintes avisam novos anúncios encontrados e quedas de preço dentro dos filtros. **Pausar/Retomar** controla cada busca. **Histórico** mostra somente preços efetivamente lidos.

A leitura tenta HTTP direto e usa Chrome com perfil próprio em `data/olx-profile` quando necessário. **Abrir Chrome da OLX** permite conferir um bloqueio; feche essa janela antes de consultar novamente. Verificações humanas continuam manuais. Falhas preservam a última leitura. Ausência nos resultados não confirma venda, e preço anunciado não confirma conservação, pagamento nem frete. A busca pode incluir produtos novos.

Validação isolada em `http://127.0.0.1:8766`: banco e perfil próprios em `tmp/olx-verification`, sem acessar o banco do monitor principal. Iniciar com `.venv\Scripts\python.exe tmp\olx_ui_preview.py`. Essa instância apresenta apenas a área OLX.

## Conectar Mercado Livre

1. Com o Google Chrome instalado, abra **Fontes → Abrir sessão do Mercado Livre**.
2. Entre na sua conta na janela própria do monitor, aberta no Chrome normal, sem automação. Faça a verificação solicitada pelo site, se houver.
3. Feche todas as janelas desse Chrome do monitor para liberar o perfil; seu Chrome pessoal pode continuar aberto. Volte ao painel e clique **Confirmar sessão**. O app testa a busca de uma peça ativa; somente uma busca com anúncios legíveis habilita a sessão.
4. Depois da confirmação, as consultas usam esse perfil. Se o Mercado Livre recusar a consulta sem janela com 403, o app tenta o Chrome com janela e lembra esse modo após uma leitura aceita. Você pode minimizar essa janela; deixe-a aberta durante as consultas. Use **Consultar lojas agora** ou aguarde o ciclo automático.

Durante o login, consultas do Mercado Livre ficam pausadas. Se o site voltar a exigir login ou verificação, abra a sessão novamente. Bloqueios continuam sendo informados; salvar a sessão não garante que todas as consultas serão aceitas.

O perfil fica em `data/mercado-livre`, restrito ao usuário do Windows e SYSTEM e fora do versionamento. Ele contém dados de autenticação: não compartilhe essa pasta. O monitor não importa a sessão do seu Chrome de uso diário nem exporta cookies. Não envie senha ou código pelo chat.

## Conectar Shopee

Em **Fontes → Sessão da Shopee**, use **Abrir sessão da Shopee**, entre na conta no Chrome próprio, feche a janela de login e clique **Confirmar sessão da Shopee**. A confirmação testa a busca de uma peça ativa, mas aceita produtos legíveis de outros modelos: validar a sessão não depende do estoque dessa peça. Se a busca mostrar explicitamente que não há resultados, testa uma busca ampla por SSD. Uma página vazia, login ou bloqueio não confirma a sessão. Depois, use **Atualizar peça** ou aguarde o ciclo automático. O Chrome de consulta fica com janela e pode ser minimizado.

O perfil restrito fica em `data/shopee`, separado do Mercado Livre e do Chrome pessoal, sem exportação de cookies. Não compartilhe essa pasta. Login e verificação humana são feitos pelo usuário. Após o login humano informado pelo usuário, a consulta real pelo Chrome foi redirecionada para Tente Novamente Mais Tarde. O app identifica esse bloqueio sem atribuí-lo a falta de peças ou pedir novo login. Ainda não há preços reais da Shopee confirmados; testes controlados validam descoberta e preços estruturados em BRL. Preços por variação sem valor único não são confirmados; sem indicação de pagamento, o preço anunciado não vira Pix.

## Conectar Telegram

1. Encerre o monitor pelo painel.
2. Execute `Conectar-Telegram.cmd`.
3. Informe API ID e API hash do mesmo aplicativo criado em https://my.telegram.org. Digite apenas o número no ID; o hash tem 32 caracteres e não aparece enquanto você digita.
4. Informe telefone com código do país, código recebido e senha de duas etapas, se solicitada. Esses dados ficam no terminal; não cole no chat.
5. Após **Conta conectada**, execute `Iniciar-Monitor.cmd`. Na aba **Fontes**, carregue e selecione grupos de que sua conta já participa.

Se houver falha, o terminal informa a etapa e o tipo de problema sem imprimir os dados de autenticação. Feche e reabra o terminal depois de atualizar o programa.

A sessão fica em `data`, restrita ao seu usuário e SYSTEM. API ID/hash são protegidos por DPAPI. O arquivo de sessão Telegram concede acesso à conta: não compartilhe essa pasta nem a inclua em versionamento.

## Coleta e limites atuais

- Telegram recebe eventos novos; a recuperação periódica lê no máximo 100 mensagens por fonte dentro da janela de cinco minutos. Não percorre todo o histórico. A primeira ativação começa daquele momento.
- Pichau, KaBuM, Amazon, Shopee e Terabyte Shop são consultadas a cada dez minutos. Shopee exige sessão confirmada. Mercado Livre é consultado por último, a cada trinta minutos; **Consultar lojas agora** antecipa essa consulta. A descoberta considera até 12 links compatíveis da página de busca por peça, sem percorrer todas as páginas.
- Terabyte Shop: busca pública e preços da área principal do produto, sem Chrome/login. Pix exige condição explícita; o total do cartão é lido separadamente das parcelas e da tabela de alternativas. Preços antigos e recomendações não fornecem o valor atual. Produtos sem preço legível não são confirmados. A fonte segue pausa, atualização individual, marcas e corte de 12 das demais lojas.
- Pichau: preços das três peças e cupons lidos em páginas reais. Cupons não são aplicados no checkout; frete não é consultado.
- Mercado Livre: coleta prioritariamente pelos cartões da busca, lendo preço atual, vendedor, parcelas explícitas e valor com cupom da sessão. Ignora preço anterior, desconto condicionado ao saldo no Mercado Pago e outra opção de compra. Seleciona até 12 candidatos pelo preço com cupom; preço novo também permite reavaliar ofertas conhecidas que ficaram fora do corte. A busca segue o filtro de origem do frete **Local** quando disponível. Abre o produto somente se faltar preço, origem nacional ou preço no pagamento exigido pelo limite da peça; a conferência manual continua lendo o produto. Preço sem condição explícita não vira Pix. Anúncios internacionais ou com origem ainda desconhecida ficam fora do catálogo e dos avisos; registros antigos reaparecem após nova confirmação de envio local, sem apagar histórico. Usa janela própria do Chrome com a sessão salva quando necessário após 403; mensagens dos grupos continuam disponíveis.
- KaBuM: busca e produto validados em páginas públicas reais, lendo Pix, total no cartão, parcelas, vendedor e disponibilidade. Dados do produto embutidos no HTML são aceitos somente quando o ID e o título correspondem à página.
- Amazon: busca e preços de produtos coletados pelo app em páginas públicas reais, incluindo links `amzn.to`. A primeira sondagem retornou 503, mas consultas do coletor responderam e salvaram ofertas. Bloqueios continuam informados, sem preço inventado. Valor sem condição explícita não é classificado como Pix. URLs são normalizadas pelo código ASIN, preservando parâmetros de vendedor, para evitar repetições a cada busca.
- Links de outras lojas aparecem como anúncios do Telegram; a conferência automática cobre somente os hosts suportados. Preço anunciado sem pagamento explícito não é classificado como Pix.
- Avisos iguais são deduplicados por anúncio, valores e cupons. Encurtadores diferentes só podem ser agrupados depois que o destino for confirmado.
- O PC precisa permanecer ligado, sem suspensão, e o processo precisa estar ativo. O app não se instala como serviço ou tarefa automática.

## Validação

Frontend desktop: filtros recolhíveis/removíveis, comparação compacta acessível ao rolar, foco e paginação por teclado, proteção de rascunho e resultados por loja. Cupons mostram contagem de publicações, horários de publicação/consulta e conservam leitura aberta durante atualizações. Histórico explica pagamento selecionado e apresenta datas/valores em português. Rodadas atuais, capturas e distinção entre validação real e testes controlados: `UX-ITERATIONS.md`.

` .venv\Scripts\python.exe -m unittest discover -s tests -v `

347 testes passaram, incluindo consulta de water cooler com 360mm, alternativa nacional quando a busca Mercado Livre não oferece Local, atualização exclusiva de uma peça, vencimento de leituras, cupons por observação, fonte pública e limite das 12 ofertas, além de sessão persistente do Mercado Livre, alternativa com janela após 403, cupom explícito, ordenação e agrupamento, identificação/exclusão de marcas, migrações preservando dados, consulta do Mercado Livre por último e exclusão de ofertas internacionais. Compilação Python sem erros. O último lote de interface teve detector visual sem achados. No coletor real, o NV3 retornou R$ 836,92 anunciado, R$ 753,23 com cupom e 12 parcelas de R$ 80,65; esse anúncio foi depois identificado como internacional e excluído do catálogo. O navegador real confirmou cupom separado, ordenação pelo desconto, horários das consultas e exclusão/restauração de INNO3D pelo formulário. A seleção temporária de teste foi removida ao final. A leitura desconsidera anúncios do cartão Mercado Pago que antes podiam ser confundidos com o preço do produto.

No navegador real: cartões, ordenação, filtros, paginação, cadastro/edição sem salvar dados de teste, fontes, detalhes ao vivo, horários do ciclo, cópia e busca de cupons validados. Recepção de cupons reais do Telegram observada em três publicações; fontes reconectadas. O Windows aceitou o envio de aviso de teste, sem comprovação visual da exibição. Registros de cada lote e capturas estão em UX-ITERATIONS.md; retorno de foco após atualização e foco de campos inválidos conferidos nas rodadas 14 e 15.
# Aplicação de cupons do Mercado Livre

A confirmação oficial da inserção é preservada mesmo se o Mercado Livre mudar a página ou fechar o formulário após o envio. Também reconhece o redirecionamento pós-envio para `/cupons/active?source_page=int_input_code` como confirmação; abrir Meus cupons antes de enviar um código não comprova ativação. Sem esses sinais, a tentativa continua pendente e pode ser reavaliada enquanto o cupom for do dia atual. Texto técnico “spinner” não é tratado como resposta do cupom.

Os códigos do lote usam a mesma página e o mesmo modal: o campo é limpo entre as tentativas. O monitor só abre a página quando a aba está em outro endereço; se o modal fechar, reabre o formulário sem recarregar.

Na aba **Cupons**, o monitor insere automaticamente os códigos identificados exclusivamente como Mercado Livre, a cada hora, usando o perfil próprio já confirmado em **Fontes**. **Aplicar cupons agora** antecipa a fila normal; **Retentar falhas** envia somente falhas recuperáveis, sem incluir códigos novos. O agendamento roda no processo local, com o PC ligado; não depende da aba aberta. A fonte pausada ou o login pendente impedem o envio.

Somente cupons encontrados **hoje em São Paulo (UTC−3)** ficam na aba e nos lotes. Publicações, caches e registros de aplicação anteriores são apagados definitivamente, inclusive para retentativa individual. O corte usa a descoberta, não a última tentativa nem as últimas 24 horas, e é revalidado antes de cada envio. Novas mensagens registram a recepção; caches preservam a primeira descoberta durante atualizações. Registros legados usam a publicação/consulta conhecida; sem data de descoberta identificável, são removidos. A limpeza roda ao iniciar e a cada minuto, mesmo com a aba fechada; histórico de preços e cupons já adicionados à conta da loja não são alterados.

O painel do Mercado Livre reúne um registro por código, com filtros **Novos**, **Ativados**, **Falhas** e **Desativados**, busca e páginas de dez códigos. Cada registro conserva fonte, última resposta, horário e número de tentativas no SQLite. Falhas distinguem erro temporário, sessão/bloqueio, navegador, tentativa interrompida e ausência de confirmação, com retentativa individual ou em lote. Recusas por código inválido, expiração, indisponibilidade/esgotamento ou inelegibilidade não são reenviadas. A resposta **“Tivemos um problema”** deixa o cupom pendente e segue para o próximo, sem repetir o mesmo código no lote. Cinco respostas consecutivas desse erro interrompem o lote até o próximo ciclo de uma hora; qualquer outra resposta zera a contagem, que também recomeça a cada lote. Outras pendências recuperáveis continuam interrompendo a execução; recusas definitivas permitem seguir para o próximo código.

**Desativar** impede novos envios pelo monitor, inclusive de um código ainda na fila; não remove o cupom da conta do Mercado Livre. **Reativar** conserva o resultado e as tentativas; cupons já adicionados não são reenviados. A resposta oficial, mensagem explícita ou redirecionamento específico após o envio comprovam a inserção. Isso não confirma elegibilidade para todos os produtos: o preço com cupom continua sendo lido separadamente no anúncio. A aplicação aguarda as consultas em andamento e usa somente o formulário de códigos, sem compras ou alteração de pagamento. As mensagens e condições originais de todas as lojas continuam abaixo do painel.

Após sucesso ou o redirecionamento pós-envio para `/cupons/active?source_page=int_input_code`, o monitor reabre imediatamente a página inicial de inserção. O código confirmado não é reenviado, mesmo se a reabertura falhar. Recusas sem esse redirecionamento reaproveitam o formulário disponível.
