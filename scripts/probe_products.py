import asyncio
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shops import Shops, product_offer

async def main():
    shops = Shops()
    for component in [{'kind':'gpu','query':'rtx 5060'}, {'kind':'psu','query':'corsair cx750'}, {'kind':'ssd','query':'kingston nv3 1tb','capacity_gb':1000}]:
        try:
            urls = await shops.discover('Pichau', component)
            print(component['kind'],'links',len(urls),flush=True)
            html, url = await shops.fetch(urls[0])
            (ROOT / 'data' / ('probe-product-' + component['kind'] + '.html')).write_text(html,encoding='utf-8')
            result = product_offer(html,url,component)
            print({key:result.get(key) for key in ['title','pix','card','announced','installments','availability']},flush=True)
        except Exception as exc:
            print(component['kind'],type(exc).__name__,str(exc),flush=True)
    await shops.close()

if __name__=='__main__':
    asyncio.run(main())
