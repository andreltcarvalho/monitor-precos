# Correção da consulta de water cooler — 2026-10-02

Escopo confirmado: manter Rise Mode, ARGB e cadastro; corrigir reconhecimento de 360/360mm e investigar envio nacional Mercado Livre.

- core.py: reconhecer dimensões em mm na busca por texto sem confundir modelos alfanuméricos ou tamanhos diferentes.
- shops.py: permitir links de produto water cooler na Pichau; verificar evidência do filtro nacional Mercado Livre antes de mudar sua regra.
- Testes: correspondência de tamanho, rejeição de marca/iluminação/tamanho incompatíveis, descoberta e consulta restrita à peça.
- Validação: suíte Python, compilação, consulta real e interface. Não alterar configurações, sessões nem históricos.

Evidências: Amazon publicou Rise Mode 360mm ARGB, recusado pela correspondência anterior. Pichau excluía links water-cooler por prefixo. KaBuM retornou nenhum produto para 360, mas cinco links compatíveis para 360mm; normalização somente da consulta enviada a essa loja. Mercado Livre real retornou anúncios sem nenhum link SHIPPING/Local; descoberta agora permite esses candidatos, mantendo exclusão de cartões internacionais e confirmação nacional obrigatória no produto para catálogo/avisos.

Implementação e testes: identificação de mm sem separar códigos alfanuméricos; links de water cooler Pichau; unidade na busca KaBuM; alternativa Mercado Livre sem relaxar origem. 284 testes aprovados e compilação sem erros; regressões cobrem tamanho, marca, ARGB, links, consulta KaBuM sem alteração do cadastro, origem desconhecida/internacional excluída e redirecionamento do filtro explícito recusado.

Validação real: consulta final component_id=8 conferiu cinco anúncios KaBuM, quatro Amazon e seis Mercado Livre; produtos Mercado Livre exibidos têm origem local confirmada. Pichau não apresentou Rise Mode compatível na busca atual (retornou outras marcas), sem inventar resultados. 22 registros do water cooler preservados no banco; interface confirmou limite de 12 e seis cartões na primeira página, incluindo as três lojas. Cadastro mantido. Monitor reiniciado normalmente, PID 2268; health ativo e Telegram conectado. Evidência .impeccable/review/water-cooler-fixed.jpg.
