# Alertas no Telegram por peça

Pedido confirmado: campo de valor de notificação separado do máximo do catálogo. Avisar estritamente abaixo do valor, sem exigir o percentil de 10%, mantendo proteção contra repetições.

## Implementação
- `cloud/app.py` e `cloud/static/`: campo em Peças; configuração, pareamento privado, teste e pausa do bot em Fontes.
- `cloud/notifications.py`: critérios existentes de modelo, marca, validade e preferência; menor preço com cupom somente quando lido na loja. Limite independente do teto do catálogo. Mesmo modelo/loja agrupado; variantes distintas preservadas.
- `cloud/notifications.sql`: token no Vault, RPCs restritas à própria conta e duas tabelas privadas. Supabase avalia ofertas sincronizadas a cada minuto; até um aviso por conta/minuto. Preço já avisado não retorna a avisar, salvo se baixar. Revalidação de cadastro/leitura/preferências antes do envio.
- Falhas explícitas temporárias: até três tentativas, respeitando pausa do Telegram e leitura vigente. Entrega incerta fica bloqueada para evitar duplicação. Bot inválido/bloqueado pausa os avisos.
- Chrome e Telegram dos grupos continuam no PC; alertas e lojas HTTP não exigem painel aberto.

## Validação
- 16 testes específicos de regra e API, 68 testes cloud existentes, regressões JavaScript aprovados.
- Chrome + API ASGI com bot/banco sintéticos: campo inválido, persistência, edição, pareamento, mensagem de teste, pausa, token fora do DOM; desktop 1440/1024 sem overflow.
- `tests/cloud_notifications.sql` executado no Supabase com rollback: Vault, isolamento, permissões, limite alterado, repetição, sucesso, 429, timeout e bloqueio; nenhuma mensagem externa enviada.
- Advisor: RPCs SECURITY DEFINER são intencionais para acessar Vault/tabelas privadas; todas usam auth.uid(), search_path vazio e não aceitam owner como argumento. Acesso anônimo revogado. RLS privado sem política permite somente funções autorizadas/dono. Aviso anterior de proteção de senha mantido.
- Publicado pelo master no commit `1498a9c`, deploy Production Ready e CI Vercel success. Health 200; endpoint sem segredo 401; chamada Supabase → Vercel autenticada por Vault retornou 200/notifications vazio. Cron `monitor-precos-telegram-alerts` ativo a cada minuto, primeira execução succeeded.
- Chrome autenticado em produção: sete páginas sem erro JS/HTTP/overflow; campo e configuração do bot conferidos, sem alterar cadastro. Sessão de validação renovada pela rotina CloudSync existente. Bot real ainda não configurado; entrega real deve ser validada pelo botão Enviar teste depois do pareamento.
