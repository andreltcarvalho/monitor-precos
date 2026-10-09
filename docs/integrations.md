# Integrações

[Documentação](README.md) · [Primeiros passos](getting-started.md)

## Fontes e execução

| Fonte | Execução | Configuração |
| --- | --- | --- |
| Pichau, KaBuM, Amazon, Terabyte | HTTP na nuvem | Ativar em Fontes. |
| Mercado Livre, Shopee | Chrome no PC | Login no perfil próprio. |
| OLX | HTTP no PC, Chrome se necessário | Cadastrar uma busca em Usados. |
| Grupos do Telegram | Telethon no PC | Conectar sua conta e selecionar grupos. |
| Cupons públicos | HTTP na nuvem | Consulta automática ou botão em Cupons. |
| Ativação de cupons do Mercado Livre | Chrome no PC | Sessão do Mercado Livre confirmada. |
| Alertas no Telegram | Bot API na nuvem | Conectar bot exclusivo ao seu chat privado. |

Os grupos fornecem mensagens ao coletor; o bot entrega avisos a você. São duas integrações separadas, com credenciais diferentes.

## Mercado Livre

1. Com o coletor conectado, abra a configuração do Mercado Livre em **Fontes** e clique em **Abrir sessão**.
2. Entre na conta no Chrome próprio do monitor. Resolva manualmente login e verificações solicitadas pelo site.
3. Feche todas as janelas desse perfil de login; seu Chrome pessoal pode continuar aberto.
4. Volte ao painel e use **Confirmar sessão**.

A confirmação consulta uma busca para verificar que a página é legível. Durante o login, as consultas ficam pausadas. O app tenta usar o Chrome com janela quando uma consulta sem janela recebe 403. A janela de coleta pode ficar minimizada, mas deve permanecer disponível durante as consultas.

O coletor lê os cartões da busca antes de abrir produtos individuais. Usa a página do produto quando faltam dados necessários ou numa conferência manual. O preço com cupom é lido da sessão; não é calculado a partir de um código publicado. Envio internacional ou origem desconhecida não entra no catálogo.

## Shopee

Abra a sessão própria em **Fontes**, faça o login, feche a janela de login e confirme. A confirmação procura produtos legíveis; se a peça não tiver resultados, pode testar uma busca mais ampla.

A consulta usa Chrome com janela. Uma página vazia, bloqueada ou de login não confirma a sessão. Valores variáveis sem preço único não são tratados como um preço confirmado. Login salvo não garante que a loja aceite consultas futuras.

## OLX

Cadastre uma URL de busca localizada ou informe produto, UF e cidade em **Usados**. Prefira um link já localizado quando o seletor da loja estiver indisponível.

Use **Abrir Chrome da OLX** para conferir um bloqueio ou uma verificação. Feche a janela aberta manualmente antes de consultar novamente. O perfil é separado dos perfis do Mercado Livre e da Shopee.

## Grupos do Telegram

Com o monitor parado:

```powershell
.\Conectar-Telegram.cmd
```

1. Obtenha **API ID** e **API hash** do mesmo aplicativo em [my.telegram.org](https://my.telegram.org).
2. Informe os dados no terminal, seguido de telefone com código do país, código de login e senha de duas etapas, se solicitada.
3. Inicie o monitor e adicione/ative em **Fontes** os grupos dos quais sua conta participa.

O coletor recebe mensagens novas. A recuperação de mensagens recentes é limitada à janela de cinco minutos; a primeira ativação não importa nem avisa o histórico inteiro do grupo.

Essas credenciais são da conta Telegram/Telethon. Não use o token do BotFather nesse configurador.

## Bot de alertas

1. No [BotFather](https://t.me/BotFather), crie um bot exclusivo com `/newbot`.
2. Em **Fontes → Alertas no Telegram → Configurar ou trocar o bot**, cole o token no campo protegido.
3. Abra **Abrir meu bot**, toque em **Iniciar** e volte ao painel.
4. Use **Confirmar conexão** e **Enviar teste**.
5. Configure **Avisar abaixo de** nas peças que deseja acompanhar.

O link de pareamento vale por 15 minutos. Gere outro conectando novamente se ele expirar. Use um bot exclusivo: outra integração que consuma suas mensagens ou configure webhook pode impedir o pareamento.

**Pausar alertas** suspende os avisos sem pausar a coleta de ofertas. [Entenda a regra do preço e da repetição](usage.md#alertas-no-telegram).

## Problemas comuns

| Situação | O que conferir |
| --- | --- |
| Pedido aguardando o PC | Coletor ativo, mesma conta no painel e no configurador, PC sem suspensão. Veja Atividade. |
| Sessão salva, mas consulta recebe 403/login | Abra a sessão da loja e confira a página no perfil próprio. |
| Shopee sem produtos legíveis | Confira bloqueio, login ou carregamento incompleto; isso não comprova falta de estoque. |
| OLX traz uma região ampla | Use uma busca já localizada e confira UF/cidade; Piracicaba possui rota própria. |
| Nenhuma mensagem de grupo | Conta participa do grupo e fonte ativa. Ofertas antigas não são importadas. |
| Bot conectado, mas sem aviso | Campo de alerta preenchido, oferta válida abaixo dele e nenhum aviso igual já entregue. |
| Bot bloqueado/token recusado | Abra o bot, desbloqueie-o ou reconecte o token, envie teste e reative os alertas. |

Uma falha de fonte não é uma busca vazia. Últimos registros e histórico são preservados, com o estado da consulta disponível no painel.
