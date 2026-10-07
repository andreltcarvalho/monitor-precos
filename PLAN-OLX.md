# OLX — usados

Escopo aprovado: acompanhar buscas de usados na OLX, cadastradas por URL ou por produto, UF, cidade e teto opcional. Integração local; Chrome com perfil próprio como alternativa à leitura HTTP. Sem Facebook neste lote.

- `olx.py`: validação, leitura dos cartões reais, perfil Chrome, persistência aditiva e ciclo de consulta/avisos.
- `olx_ui.py`, `app.py`: aba Usados no padrão atual, cadastro, buscas pausáveis, resultado e histórico por anúncio.
- `monitor.py`: iniciar/parar o ciclo junto ao serviço existente.
- `tests/test_olx.py`: isolamento de anúncios/preços, URLs, filtros, primeira consulta, deduplicação, queda, falhas e pausa.

Regras: primeira leitura estabelece referência sem avisar o acervo; avisar novos anúncios encontrados e quedas dentro dos filtros. Ler até 50 anúncios recentes por busca/ciclo; ausência na busca não confirma venda. Não aplicar top 12/ranking de peças a usados. Identidade pelo ID da OLX. Falha conserva dados e não renova leitura. Condição e pagamento desconhecidos não são inferidos.

Evidência inicial: HTTP direto retornou Cloudflare 403. Chrome normal com perfil exclusivo leu HTTP 200 e 50 cartões em 06/10/2026. Cidade é resolvida pelo seletor oficial, sem inventar caminhos regionais.

Validação: testes específicos e regressão completa, compileall, coleta real pelos métodos novos, cadastro e resultados na interface local.

Implementação concluída. 22 testes OLX e 408 gerais passaram; compilação limpa. Chrome leu 22 anúncios por campos e 26 por URL em Piracicaba. Cadastro, pausa, consulta manual, histórico durante atualização e foco na paginação/fechamento verificados. Notificações testadas com substituto, sem afirmar toast visual. Instância isolada 8766 com banco/perfil separados e ciclo ativo; monitor principal 8765 preservado após aviso de trabalho paralelo na tela de cupons. Ajustes finais disponíveis na instância isolada e no próximo reinício do principal.

Revisão visual final: ship, após recapturas estáveis e correção de foco. DESIGN.md preservado: nenhum token/regra visual durável alterado. Sem overflow em 390px. Capturas finais `olx-desktop.jpg`, `olx-form.jpg`, `olx-history.jpg` e `olx-mobile.jpg` em `.impeccable/review`.
