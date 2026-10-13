import json
import unittest
from unittest.mock import AsyncMock
from core import matches
from shops import Shops, search_links

PART={'kind':'custom','query':'rtx 5060 ti 16gb'}

class CatalogueDiscoveryTests(unittest.TestCase):
    def page(self,rows,serialized=False):
        data={'catalogServer':{'data':rows}}
        payload={'props':{'pageProps':{'data':json.dumps(data) if serialized else data}}}
        return '<script id="__NEXT_DATA__" type="application/json">'+json.dumps(payload)+'</script>'

    def test_full_hydrated_catalogue_sorted_by_listing_price_and_not_seo_subset(self):
        rows=[{'code':i+100,'name':'MSI RTX5060Ti 16G','friendlyName':'msi-'+str(i),
               'available':True,'priceWithDiscount':5000-i*10} for i in range(30)]
        for serialized in (False,True):
            html=self.page(rows,serialized)
            links=search_links(html,'https://www.kabum.com.br/busca/rtx',PART,limit=None)
            self.assertEqual(len(links),30)
            self.assertIn('/produto/129/',links[0])
            self.assertEqual(len(search_links(html,'https://www.kabum.com.br/busca/rtx',PART)),12)

    def test_excludes_other_memory_pcs_ignored_brands_unavailable_and_external_urls(self):
        titles=['MSI RTX 5060 Ti 16GB','MSI RTX 5060 Ti 8GB','PC Gamer RTX 5060 Ti 16GB','ASUS RTX 5060 Ti 16GB','MSI RTX 5060 Ti 16GB']
        rows=[{'code':i+100,'name':title,'available':i!=4,'externalUrl':'https://evil.test/a'} for i,title in enumerate(titles)]
        part=dict(PART,ignored_brands=['ASUS'])
        links=search_links(self.page(rows),'https://www.kabum.com.br/busca/x',part,limit=None)
        self.assertEqual(links,['https://www.kabum.com.br/produto/100/'])

    def test_compact_gpu_names_keep_model_memory_and_accessory_boundaries(self):
        self.assertTrue(matches(PART,'Palit GeForce RTX5060Ti INFINITY 3 16G GDDR7'))
        self.assertFalse(matches(PART,'Palit RTX5060 16GB'))
        self.assertFalse(matches(PART,'MSI RTX5060Ti 8GB'))
        self.assertFalse(matches(PART,'Suporte para RTX5060Ti 16GB'))
        self.assertFalse(matches({'kind':'gpu'},'RTX5060Ti 8GB'))
        self.assertTrue(matches({'kind':'custom','query':'rx 9060 xt 16gb'},'ASRock RX9060XT 16G'))

    def test_amazon_tracking_links_do_not_duplicate_discovery_or_waste_checks(self):
        html=''.join('<a href="https://www.amazon.com.br/title/dp/B012345678/ref=sr_'+str(i)+'?keywords=rtx&dib='+str(i)+'">RTX 5060 Ti 16GB</a>' for i in range(5))
        links=search_links(html,'https://www.amazon.com.br/s',PART,limit=None)
        self.assertEqual(len(links),1)
        self.assertIn('/dp/B012345678/',links[0])

class DiscoveryTotalsTests(unittest.IsolatedAsyncioTestCase):
    async def test_result_total_survives_twelve_check_budget(self):
        shops=Shops()
        try:
            shops._search_page=AsyncMock(return_value=(CatalogueDiscoveryTests().page([
                {'code':i+100,'name':'RTX 5060 Ti 16GB','priceWithDiscount':3000+i} for i in range(30)]),'https://www.kabum.com.br/busca/x'))
            urls=await shops.discover('KaBuM',PART)
            self.assertEqual((len(urls),urls.total),(12,30))
        finally:await shops.close()
