# Primeiros passos

[Documentação](README.md) · [Integrações](integrations.md)

## Usar o painel

1. Abra o [painel publicado](https://monitor-precos-snowy.vercel.app).
2. Crie sua conta, confirme o e-mail e entre. Não há login ou senha compartilhados.
3. Em **Peças**, cadastre o modelo que deseja acompanhar. O preço máximo e as marcas ignoradas são opcionais.
4. Em **Fontes**, confira quais lojas estão ativas. Pichau, KaBuM, Amazon e Terabyte são consultadas na nuvem.

As consultas online e o histórico não precisam do PC ligado. Mercado Livre, Shopee, OLX, grupos do Telegram e ativação de cupons precisam do coletor local.

## Instalar o coletor no Windows

Requisitos: Windows 10/11, Python 3.12 disponível por `py -3.12`, Git e Google Chrome. Node.js só é necessário para os testes JavaScript.

No PowerShell:

```powershell
git clone https://github.com/andreltcarvalho/monitor-precos.git
cd monitor-precos
.\Instalar.cmd
```

O instalador cria `.venv/` e instala as dependências. Se preferir fazer isso manualmente:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Conectar sua conta

Execute o configurador com o monitor parado:

```powershell
.\Conectar-Nuvem.cmd
```

Informe o endereço do painel, o e-mail e a senha da sua conta. O configurador salva tokens de sessão protegidos pelo Windows; não salva a senha.

Se também quiser receber mensagens de grupos, configure a conta do Telegram com `Conectar-Telegram.cmd` antes de iniciar. [Veja o procedimento](integrations.md#grupos-do-telegram).

## Iniciar e conferir

```powershell
.\Iniciar-Monitor.cmd
```

O endereço local `http://127.0.0.1:8765/` redireciona para o painel publicado: a interface é a mesma. Para conferir o coletor:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

`running: true` confirma que o monitor iniciou. No painel, **Fontes** mostra a presença do PC; a sincronização ocorre a cada minuto. Faça alterações de peças e preferências pelo painel, que as envia ao coletor.

Mantenha o processo ativo e o PC sem suspensão para as fontes locais funcionarem. Fechar a aba não encerra o monitor. Para parar, interrompa o processo no terminal com **Ctrl+C**.

## Depois da instalação

- Conecte as sessões em [Integrações](integrations.md).
- Configure os [alertas por preço](usage.md#alertas-no-telegram).
- Consulte [problemas comuns](integrations.md#problemas-comuns) se uma loja não responder.

Ofertas e sessões locais ficam em `data/`. Não compartilhe essa pasta. [Saiba o que é sincronizado](security.md).
