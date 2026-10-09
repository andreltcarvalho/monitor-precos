# Uso do app

[Documentação](README.md) · [Conectar fontes](integrations.md)

## Peças e limites

Em **Peças**, cadastre um nome e a busca pelo modelo desejado. Use busca por texto para modelos diferentes das identificações específicas do formulário. Para o Kingston NV3, informe a capacidade em GB; 1 TB corresponde a 1000.

| Campo | Efeito |
| --- | --- |
| **Preço máximo** | Filtra a lista de ofertas, inclusive no valor igual ao limite. |
| **Pagamento do limite** | Escolhe Pix ou total no cartão para esse filtro. |
| **Avisar abaixo de** | Envia alertas pelo Telegram estritamente abaixo desse valor. |
| **Ignorar marcas** | Exclui os fabricantes escolhidos das ofertas e dos avisos. |
| **Monitorar esta peça** | Ativa ou pausa o acompanhamento. |

Vazio remove o limite correspondente. O valor do alerta é separado do preço máximo do catálogo. Alterar o máximo atualiza a lista usando os preços já salvos, sem esperar nova consulta.

O app não presume Pix quando a loja não informa a condição. Por isso, uma oferta sem preço conhecido no pagamento escolhido pode ficar fora do teto, mesmo tendo um preço anunciado menor.

## Ofertas

**Mais baratas** mostra até 12 ofertas por peça, somando todas as lojas, em páginas de seis cartões. O preço máximo é aplicado antes desse corte; filtros de texto e loja atuam na seleção resultante.

Repetições do mesmo modelo/vendedor na mesma loja são agrupadas. Variantes como White e V2, outras lojas e outros vendedores ficam separadas. Os anúncios originais continuam em **Detalhes**.

O cartão destaca o menor preço disponível e sua condição. **Ver oferta** abre a loja; **Detalhes** reúne título completo, vendedor, pagamentos, horários e origem da leitura.

| Ação | O que faz |
| --- | --- |
| **Atualizar lista** | Recarrega resultados já salvos. |
| **Atualizar esta peça** | Busca novos anúncios e confere preços dessa peça nas lojas ativas. |
| **Conferir** em Detalhes | Relê o anúncio específico. |
| **Favoritar** | Guarda o anúncio na seleção de favoritas. |
| **Ocultar** | Retira do catálogo e dos avisos, preservando histórico. |
| **Comparar** | Compara até três ofertas da mesma peça nesta aba. |

Favoritar não força uma oferta acima do corte a ser consultada. Ofertas conhecidas acima do 12º preço deixam as consultas automáticas; novas ofertas mais baratas podem entrar. Favoritas e ocultas continuam acessíveis nas seleções próprias.

Consultas de Mercado Livre e Shopee entram na fila do PC. Veja pedidos pendentes e resultados em **Atividade**. Filtros e paginação não iniciam uma nova busca.

## Preços, cupons e validade

O app separa Pix, total no cartão, valor da parcela e preço anunciado. Cupom publicado não é desconto confirmado; o preço explícito com cupom lido na sua sessão participa da ordenação, mas não vira Pix ou cartão sem essa informação.

| Origem da leitura | Validade usada na comparação |
| --- | --- |
| Preço conferido no Mercado Livre | 90 minutos |
| Preço conferido nas demais lojas | 30 minutos |
| Anúncio ainda não conferido do Telegram | 5 minutos |

Leituras vencidas deixam de valer como preço atual; o último valor e o histórico continuam disponíveis. Falhas de consulta não renovam a validade. Frete desconhecido não é tratado como zero.

No Mercado Livre, só ofertas com envio nacional confirmado entram no catálogo. Preço antigo riscado, propaganda de cartão e desconto condicionado ao saldo no Mercado Pago não substituem o preço do anúncio.

## Histórico

Selecione a peça e o pagamento em **Histórico** para consultar os valores observados nos últimos 7 ou 30 dias. **Melhor preço, incluindo cupom** considera o menor preço daquela leitura e pode comparar condições diferentes de pagamento.

Dias sem leitura ficam como lacunas. Desconto antigo desconhecido não é reconstruído. Frete e cupons sem preço confirmado ficam fora das estatísticas. Quando o limite de registros da consulta é atingido, o painel sinaliza histórico parcial.

## Alertas no Telegram

1. [Conecte seu bot](integrations.md#bot-de-alertas) em **Fontes → Alertas no Telegram**.
2. Em **Peças → Editar**, preencha **Avisar abaixo de (R$)**.
3. Deixe vazio para desligar os avisos dessa peça.

Basta a oferta ficar abaixo do valor: o envio não exige estar entre os 10% mais baratos. Preço igual ao limite não avisa. Cupom só reduz o valor do alerta quando foi lido na loja.

O mesmo modelo/loja não avisa novamente pelo mesmo preço ou mais caro; um preço menor pode gerar outro aviso. Ofertas ocultas, vencidas, indisponíveis, incompatíveis ou de marcas ignoradas não qualificam.

A nuvem avalia as leituras a cada minuto e envia até um aviso por conta/minuto. Não é preciso deixar o painel aberto. Novos preços das fontes que usam o PC continuam dependendo dele.

Erros temporários explícitos têm até três tentativas e respeitam a pausa pedida pelo Telegram. Uma entrega sem confirmação não é reenviada às cegas. Se o bot for bloqueado ou o token recusado, confira a conexão em Fontes e use **Enviar teste**.

Os avisos nativos do Windows seguem a regra local de atratividade: faixa dos 10% mais baratos da mesma peça/pagamento e queda mínima de 2% para repetir um aviso. Essa regra é independente do campo de alerta do Telegram.

## Cupons

**Cupons** mostra códigos encontrados hoje, separados por loja e fonte de publicação. Condições e links ficam nos detalhes. A consulta pública usa Pichau, Pelando e Melhores Cartões; esta última não abastece cupons do Mercado Livre.

| Estado | Como interpretar |
| --- | --- |
| **Novos** | Ainda não ativados pelo monitor. |
| **Ativados** | Inserção confirmada na conta do Mercado Livre; elegibilidade depende do produto. |
| **Falhas** | Motivo e possibilidade de retentativa aparecem no registro. |
| **Desativados** | O monitor não envia o código; não remove da conta da loja. |

A ativação do Mercado Livre usa o Chrome local, automaticamente a cada hora ou pelo botão do painel. **Retentar falhas** envia somente falhas recuperáveis. Códigos ativados, desativados ou definitivamente recusados não são reenviados.

Depois de sucesso, o monitor retorna da página **Meus cupons** à página de inserção. Quando o site responde **Tivemos um problema**, segue para o próximo código; cinco respostas consecutivas interrompem o lote até o próximo ciclo.

Somente cupons descobertos no dia atual em São Paulo participam da lista e dos lotes. Registros de dias anteriores são apagados; isso não remove cupons já adicionados à conta nem histórico de preços.

## Usados na OLX

Em **Usados**, adicione uma busca por link ou por produto/UF/cidade. Preço máximo e termos a excluir são opcionais. Para Piracicaba/SP, o coletor usa a rota municipal, sem depender do seletor de localização.

A primeira leitura estabelece uma referência sem avisar todo o acervo. Depois, novas ofertas e quedas dentro dos filtros podem gerar avisos. **Consultar agora**, pausa e histórico são independentes por busca.

A leitura tenta HTTP e pode usar Chrome próprio. Uma consulta bloqueada preserva os registros anteriores. Ausência nos resultados não comprova venda, e preço anunciado não confirma estado de conservação, pagamento ou frete. [Veja a conexão da OLX](integrations.md#olx).
