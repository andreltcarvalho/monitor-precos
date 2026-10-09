# Scripts de diagnóstico

[Desenvolvimento](../docs/development.md)

Execute a partir da raiz do projeto, com a venv instalada. São sondagens manuais de integrações reais, não testes de regressão offline.

| Script | O que verifica | Efeitos |
| --- | --- | --- |
| [probe_shops.py](probe_shops.py) | Acesso HTTP e Chrome sem sessão pessoal às buscas públicas. | Faz requisições e salva HTML/resultados em `data/`. |
| [probe_products.py](probe_products.py) | Descoberta e leitura de produtos Pichau das buscas de exemplo. | Faz requisições e salva HTML em `data/`; a pasta precisa existir. |
| [probe_windows.py](probe_windows.py) | Criptografia DPAPI e chamada de notificação nativa. | Envia uma notificação de teste ao Windows; não confirma sua exibição visual. |

Exemplo:

```powershell
.\.venv\Scripts\python.exe scripts/probe_shops.py
```

Resultados e HTML devem continuar fora do Git. Uma sondagem aceita não garante que a loja aceite futuras consultas pelo monitor; valide a integração pelo fluxo normal do app.
