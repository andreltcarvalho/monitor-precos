"""Validação pública de acesso. Não usa sessão do usuário nem compra produtos."""
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shops import Shops, search_links

URLS = {
    'Pichau': 'https://www.pichau.com.br/search?q=rtx%205060',
    'Mercado Livre': 'https://lista.mercadolivre.com.br/rtx-5060',
}


async def http_probe():
    client = Shops()
    results = {}
    for name, url in URLS.items():
        try:
            html, resolved = await client.fetch(url)
            print(name, 'HTTP OK', len(html), flush=True)
            (ROOT / 'data' / f'probe-{name}.html').write_text(html, encoding='utf-8')
            results[name] = {'http': 'ok', 'links': len(search_links(html, resolved, {'kind': 'gpu'}))}
        except Exception as exc:
            results[name] = {'http': str(exc)}
            print(name, 'HTTP', str(exc), flush=True)
    await client.close()
    return results


def browser_probe(results):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as engine:
        browser = engine.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context(locale='pt-BR')
        for name, url in URLS.items():
            page = context.new_page()
            try:
                response = page.goto(url, wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(3000)
                html = page.content()
                (ROOT / 'data' / f'probe-browser-{name}.html').write_text(html, encoding='utf-8')
                results[name]['browser'] = {'status': response.status if response else None,
                                            'title': page.title(),
                                            'links': len(search_links(html, page.url, {'kind': 'gpu'}))}
                print(name, 'Chrome', results[name]['browser'], flush=True)
            except Exception as exc:
                results[name]['browser'] = type(exc).__name__
                print(name, 'Chrome', type(exc).__name__, flush=True)
            finally:
                page.close()
        browser.close()


if __name__ == '__main__':
    (ROOT / 'data').mkdir(exist_ok=True)
    result = asyncio.run(http_probe())
    browser_probe(result)
    (ROOT / 'data' / 'probe-shops.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
