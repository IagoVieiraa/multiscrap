"""
Scraper para Amazon Brasil.

Ações disponíveis:
- search_product: Busca produtos por termo
- get_product_details: Obtém detalhes de um produto específico
- get_reviews: Obtém reviews de um produto
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


class AmazonScraper(BaseScraper):
    """Scraper para amazon.com.br"""

    site_id = "amazon"
    BASE_URL = "https://www.amazon.com.br"

    def __init__(self):
        super().__init__()
        self._session = None
        self._user_agent = None

    def _get_session(self) -> requests.Session:
        """
        Retorna uma sessão requests com cookies válidos da Amazon.
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

            # Navega para a home da Amazon para obter cookies
            page.goto(self.BASE_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)  # Espera carregar completamente

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
                domain=cookie.get("domain", ".amazon.com.br"),
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

    def search_product(self, payload: dict) -> ScraperResult:
        """
        Busca produtos na Amazon.
        """
        query = payload.get("query")
        if not query:
            return ScraperResult(status="failed", error="Campo 'query' é obrigatório")

        self.logger.info(f"Buscando '{query}' na Amazon")

        try:
            session = self._get_session()
            url = f"{self.BASE_URL}/s?k={query}"
            response = session.get(url, headers=self._get_headers(), timeout=15)

            # Se receber erro, tenta renovar sessão uma vez
            if response.status_code >= 400 or "Algo deu errado" in response.text:
                self.logger.warning("Sessão inválida, renovando cookies...")
                session = self._refresh_session()
                response = session.get(url, headers=self._get_headers(), timeout=15)

            response.raise_for_status()
        except requests.RequestException as e:
            self.logger.error(f"Erro ao buscar '{query}': {e}")
            return ScraperResult(status="failed", error=str(e))

        soup = BeautifulSoup(response.text, 'html.parser')
        products = []
        search_results = soup.select('div[data-component-type="s-search-result"]')

        for result in search_results:
            asin = result.get('data-asin')
            if not asin:
                continue

            product_data = {
                "asin": asin,
                "url": f"{self.BASE_URL}/dp/{asin}",
                "title": None,
                "price": None,
                "original_price": None,
                "currency": "BRL",
                "rating": None,
                "reviews_count": None,
                "prime": bool(result.select_one('i.a-icon-prime')),
                "thumbnail": None,
                "badges": [],
                "sponsored": "Patrocinado" in result.get_text()
            }

            # Title
            title_element = result.select_one('h2.a-text-normal')
            if title_element:
                product_data['title'] = title_element.get_text(strip=True)

            # Price
            price_element = result.select_one('span.a-price > span.a-offscreen')
            if price_element:
                product_data['price'] = string_formatter.parse_price(price_element.get_text())

            # Original Price
            original_price_element = result.select_one('span.a-text-price > span.a-offscreen')
            if original_price_element:
                product_data['original_price'] = string_formatter.parse_price(original_price_element.get_text())

            # Rating and Reviews
            reviews_block = result.select_one('div[data-cy="reviews-block"]')
            if reviews_block:
                rating_text_element = reviews_block.select_one('span.a-icon-alt')
                if rating_text_element:
                    try:
                        # Ex: "4,2 de 5 estrelas"
                        rating_match = re.search(r'(\d,\d)', rating_text_element.get_text())
                        if rating_match:
                            product_data['rating'] = float(rating_match.group(1).replace(',', '.'))
                    except (ValueError, TypeError, AttributeError):
                        self.logger.warning(f"Não foi possível extrair a avaliação de: {rating_text_element.get_text(strip=True)}")

                reviews_count_element = reviews_block.select_one('a[href*="#customerReviews"] span')
                if reviews_count_element:
                    try:
                        # Ex: "(522)"
                        reviews_str = reviews_count_element.get_text(strip=True).strip('()')
                        product_data['reviews_count'] = int(reviews_str.replace('.', ''))
                    except (ValueError, TypeError):
                         self.logger.warning(f"Não foi possível extrair número de reviews de: {reviews_count_element.get_text(strip=True)}")

            # Thumbnail
            thumbnail_element = result.select_one('img.s-image')
            if thumbnail_element:
                product_data['thumbnail'] = thumbnail_element.get('src')
            
            # Badges
            badge_elements = result.select('span.a-badge-text')
            for badge in badge_elements:
                product_data['badges'].append(badge.get_text(strip=True))

            products.append(product_data)

        return ScraperResult(
            status="completed",
            data={
                "products": products,
                "total_found": len(products),
                "query": query,
                "filters_applied": payload
            }
        )

    def get_product_details(self, payload: dict) -> ScraperResult:
        """
        Obtém detalhes de um produto específico.
        """
        # TODO: Implementar scraping real
        return ScraperResult(status="pending", error="Não implementado")

    def get_reviews(self, payload: dict) -> ScraperResult:
        """
        Obtém reviews de um produto.
        """
        # TODO: Implementar scraping real
        return ScraperResult(status="pending", error="Não implementado")
    
    def search_categories(self, payload: dict) -> ScraperResult:
        """
        Busca categorias de produtos na Amazon.
        """
        ...
if __name__ == "__main__":
    scraper = AmazonScraper()
    result = scraper.search_product({"query": "notebook"})
    print(result)