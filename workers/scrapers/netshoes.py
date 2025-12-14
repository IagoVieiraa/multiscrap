"""
Scraper para Netshoes Brasil.

Ações disponíveis:
- search_category: Busca produtos por categoria (ex: "calcados/chinelos", "roupas/calca")
- get_product_details: Obtém detalhes de um produto específico
"""
import re
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

try:
    from ..base import BaseScraper, ScraperResult
    from ..utils import string_formatter
except ImportError:
    # Fallback para execução direta do arquivo
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from base import BaseScraper, ScraperResult
    from utils import string_formatter


class NetshoesScraper(BaseScraper):
    """Scraper para netshoes.com.br"""

    site_id = "netshoes"
    BASE_URL = "https://www.netshoes.com.br"

    def __init__(self):
        super().__init__()
        self._session = None
        self._user_agent = None

    def _get_session(self) -> requests.Session:
        """
        Retorna uma sessão requests com cookies válidos da Netshoes.
        Usa Playwright para obter cookies se necessário.
        """
        if self._session is not None:
            return self._session

        self.logger.info("Obtendo cookies via Playwright...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                locale="pt-BR",
                viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()

            # Navega para a home da Netshoes para obter cookies
            page.goto(self.BASE_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            # Captura cookies e user-agent
            cookies = context.cookies()
            self._user_agent = page.evaluate("() => navigator.userAgent")

            browser.close()

        # Cria sessão requests com os cookies
        self._session = requests.Session()
        for cookie in cookies:
            self._session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain", ".netshoes.com.br"),
                path=cookie.get("path", "/")
            )

        self.logger.info(f"Cookies obtidos: {len(cookies)} cookies")
        return self._session

    def _get_headers(self) -> dict:
        """Retorna headers para requisições."""
        return {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'accept-language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'user-agent': self._user_agent or 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Chromium";v="123", "Google Chrome";v="123"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
        }

    def _refresh_session(self):
        """Força renovação da sessão (útil quando cookies expiram)."""
        self._session = None
        self._user_agent = None
        return self._get_session()

    def _parse_rating(self, stars_element) -> float | None:
        """
        Extrai o rating a partir do elemento stars.
        O rating é calculado com base no width do .uncover (cobertura das estrelas).
        """
        if not stars_element:
            return None

        uncover = stars_element.select_one('.uncover')
        if not uncover:
            return 5.0  # Se não há uncover, todas as estrelas estão preenchidas

        style = uncover.get('style', '')
        # Extrai o width (ex: "width: 16.6%")
        width_match = re.search(r'width:\s*([\d.]+)%', style)
        if width_match:
            uncover_percent = float(width_match.group(1))
            # uncover representa a parte NÃO preenchida
            # Se uncover é 0%, rating é 5.0
            # Se uncover é 100%, rating é 0.0
            filled_percent = 100 - uncover_percent
            rating = (filled_percent / 100) * 5
            return round(rating, 1)

        return None

    def _parse_discount(self, discount_text: str) -> int | None:
        """
        Extrai o percentual de desconto do texto (ex: "-52% OFF" -> 52).
        """
        if not discount_text:
            return None
        match = re.search(r'-?(\d+)%', discount_text)
        if match:
            return int(match.group(1))
        return None

    def _fetch_page_with_playwright(self, url: str) -> str:
        """
        Busca uma página usando Playwright para renderizar JavaScript.
        Necessário porque Netshoes usa Vue.js para renderizar preços dinamicamente.
        """
        self.logger.info(f"Buscando página via Playwright: {url}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                locale="pt-BR",
                viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()

            page.goto(url, wait_until="domcontentloaded")
            # Espera os preços carregarem (Vue.js renderiza dinamicamente)
            page.wait_for_timeout(3000)

            # Tenta esperar pelo seletor de preço para garantir que carregou
            try:
                page.wait_for_selector('[data-price="price"]', timeout=5000)
            except Exception:
                self.logger.warning("Seletor de preço não encontrado, continuando...")

            html_content = page.content()
            browser.close()

        return html_content

    def search_category(self, payload: dict) -> ScraperResult:
        """
        Busca produtos em uma categoria da Netshoes.

        Args:
            payload: {
                "category": str - Caminho da categoria (ex: "calcados/chinelos", "roupas/calca")
                "page": int - Número da página (opcional, default 1)
            }

        Returns:
            ScraperResult com lista de produtos
        """
        category = payload.get("category")
        if not category:
            return ScraperResult(status="failed", error="Campo 'category' é obrigatório")

        page = payload.get("page", 1)

        self.logger.info(f"Buscando categoria '{category}' na Netshoes (página {page})")

        try:
            # A URL da categoria pode incluir paginação
            url = f"{self.BASE_URL}/{category}"
            if page > 1:
                url += f"?page={page}"

            # Usa Playwright para renderizar a página (Vue.js)
            html_content = self._fetch_page_with_playwright(url)
        except Exception as e:
            self.logger.error(f"Erro ao buscar categoria '{category}': {e}")
            return ScraperResult(status="failed", error=str(e))

        soup = BeautifulSoup(html_content, 'html.parser')
        products = []

        # Encontra o container de produtos
        product_list = soup.select_one('.product-list__items')
        if not product_list:
            self.logger.warning("Container de produtos não encontrado")
            return ScraperResult(
                status="completed",
                data={
                    "products": [],
                    "total_found": 0,
                    "category": category,
                    "page": page
                }
            )

        # Cada produto é um card com data-code
        cards = product_list.select('div.card[data-code]')

        for card in cards:
            sku = card.get('data-code')
            if not sku:
                continue

            # Extrai dados do link principal
            link = card.select_one('a.card__link')
            if not link:
                continue

            product_data = {
                "sku": sku,
                "url": f"{self.BASE_URL}{link.get('href', '')}",
                "product_id": link.get('data-smarthintproductid'),
                "department": link.get('data-department'),
                "product_type": link.get('data-producttype'),
                "brand": link.get('data-brand'),
                "name": link.get('data-name'),
                "price": None,
                "original_price": None,
                "currency": "BRL",
                "discount_percent": None,
                "payment_method": None,
                "rating": None,
                "thumbnail": None,
                "badges": [],
                "shipping_info": None,
                "delivered_by": None,
            }

            # Nome (backup do data-name)
            name_element = card.select_one('.card__description--name')
            if name_element and not product_data['name']:
                product_data['name'] = name_element.get_text(strip=True)

            # Imagem
            img_element = card.select_one('img.image')
            if img_element:
                product_data['thumbnail'] = img_element.get('src')

            # Desconto
            discount_element = card.select_one('.discount-badge')
            if discount_element:
                discount_text = discount_element.get_text(strip=True)
                product_data['discount_percent'] = self._parse_discount(discount_text)


            # Preço original (riscado)
            original_price_element = card.select_one('del')
            if original_price_element:
                product_data['original_price'] = string_formatter.parse_price(
                    original_price_element.get_text(strip=True)
                )

            # Preço atual - usa o seletor data-price="price" diretamente
            current_price_element = card.select_one('[data-price="price"]')
            if current_price_element:
                product_data['price'] = string_formatter.parse_price(
                    current_price_element.get_text(strip=True)
                )

            # Método de pagamento (ex: "no Pix")
            payment_method_element = card.select_one('.full-mounted__payment-method')
            if payment_method_element:
                payment_text = payment_method_element.get_text(strip=True)
                if payment_text:
                    product_data['payment_method'] = payment_text

            # Rating (estrelas)
            stars_element = card.select_one('.stars')
            if stars_element:
                product_data['rating'] = self._parse_rating(stars_element)

            # Badges promocionais
            badge_elements = card.select('.promotional-badge .badge')
            for badge in badge_elements:
                badge_text = badge.get_text(strip=True)
                if badge_text:
                    product_data['badges'].append(badge_text)

            # Informação de entrega
            shipping_element = card.select_one('.shipping-navigation--fulfillment')
            if shipping_element:
                product_data['shipping_info'] = shipping_element.get_text(strip=True)

            # Enviado por
            delivered_by_element = card.select_one('.fullfilment__delivered-by')
            if delivered_by_element:
                # Extrai apenas o texto, ignorando imagens
                delivered_text = delivered_by_element.get_text(strip=True)
                # Remove "Enviado por" se presente
                product_data['delivered_by'] = delivered_text.replace('Enviado por', '').strip()

            products.append(product_data)

        return ScraperResult(
            status="completed",
            data={
                "products": products,
                "total_found": len(products),
                "category": category,
                "page": page,
                "filters_applied": payload
            }
        )

    def get_product_details(self, payload: dict) -> ScraperResult:
        """
        Obtém detalhes de um produto específico.
        """
        # TODO: Implementar scraping da página de detalhes do produto
        return ScraperResult(status="pending", error="Não implementado")


if __name__ == "__main__":
    scraper = NetshoesScraper()
    # Teste com a categoria Roupas > Calça (Infantil)
    result = scraper.search_category({"category": "infantil/roupas/calcas"})
    print(f"Status: {result.status}")
    print(f"Total encontrado: {result.data.get('total_found', 0)}")
    if result.data.get('products'):
        for i, product in enumerate(result.data['products'][:3]):
            print(f"\n--- Produto {i+1} ---")
            print(f"Nome: {product['name']}")
            print(f"Marca: {product['brand']}")
            print(f"SKU: {product['sku']}")
            print(f"Preço: R$ {product['price']}")
            print(f"Preço original: R$ {product['original_price']}")
            print(f"Desconto: {product['discount_percent']}%")
            print(f"Rating: {product['rating']}")
            print(f"Entrega: {product['shipping_info']}")