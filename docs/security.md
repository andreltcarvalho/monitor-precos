# Credenciais e privacidade

[Documentação](README.md) · [Integrações](integrations.md)

## O que fica em cada lugar

| Dado | Armazenamento |
| --- | --- |
| Ofertas e histórico locais | SQLite em `data/`. |
| Login de Mercado Livre/Shopee/OLX | Perfis próprios do Chrome em `data/`. |
| Conta Telegram dos grupos | Sessão local; API ID/hash protegidos por Windows/DPAPI. |
| Conexão PC/nuvem | Tokens em `data/cloud-credentials.bin`, protegidos por DPAPI; senha não salva. |
| Ofertas, cadastros e histórico cloud | Postgres, restritos à conta por RLS. |
| Token do bot de alertas | Supabase Vault e configuração privada da conta. |
| Segredo do agendamento | Ambiente do servidor e Vault. |

Os perfis das lojas são separados do Chrome pessoal. O monitor não importa cookies do seu navegador de uso diário nem exporta as sessões para a nuvem.

A sincronização envia somente os campos permitidos em `cloud_sync.py`. Não envia arquivos de sessão, telefone ou credenciais do Telegram dos grupos. O token do bot não aparece nas respostas do painel e não é exportado ao coletor; as RPCs de configuração são restritas ao próprio usuário.

## Login e autorização

Não há credencial padrão. Cada pessoa cria a própria conta no Supabase Auth pelo painel. A API valida a sessão e o proprietário; um usuário autenticado não recebe acesso aos registros de outra conta.

O app não usa chave administrativa no frontend ou no coletor. As consultas agendadas têm um segredo próprio. Os schemas `monitor_private`, `vault` e `net` ficam fora da Data API.

## Antes de publicar ou compartilhar

- Não inclua `data/`, `.env*`, bancos, perfis, cookies, tokens ou sessões no commit.
- Mantenha capturas, respostas HTML de sondagens e dumps pessoais em `tmp/` ou `data/`, ignorados pelo Git.
- Nunca cole senha, código de login ou token em issues, logs ou screenshots.
- Confira `git status` e o conteúdo do diff antes do push.

A captura usada no README foi gerada com dados fictícios, sem credenciais ou acesso à conta real.

## Backup local

Pare o coletor antes de copiar `data/`. Essa pasta contém dados de autenticação e deve ser tratada como privada. Credenciais protegidas por DPAPI dependem do usuário/Windows que as criou; copiar para outro PC não equivale a migrar o login.

A ausência de um arquivo no Git não impede compartilhamento acidental por um ZIP ou backup. Para mostrar o projeto, compartilhe o repositório e capturas demonstrativas, não a pasta de dados.
