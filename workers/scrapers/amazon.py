"""
Scraper para Amazon Brasil.

Ações disponíveis:
- search_product: Busca produtos por termo
- get_product_details: Obtém detalhes de um produto específico
- get_reviews: Obtém reviews de um produto
"""
import sys
import re
import requests
from bs4 import BeautifulSoup
sys.path.insert(0, '..')

from base_scraper import BaseScraper, ScraperResult


class AmazonScraper(BaseScraper):
    """Scraper para amazon.com.br"""

    site_id = "amazon"
    BASE_URL = "https://www.amazon.com.br"

    def search_product(self, payload: dict) -> ScraperResult:
        """
        Busca produtos na Amazon.
        """
        query = payload.get("query")
        if not query:
            return ScraperResult(status="failed", error="Campo 'query' é obrigatório")

        self.logger.info(f"Buscando '{query}' na Amazon")

        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'upgrade-insecure-requests': '1',
        }

        try:
            url = f"{self.BASE_URL}/s?k={query}"
            response = requests.get(url, headers=headers, timeout=15)
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
            title_element = result.select_one('h2 a.a-link-normal span.a-text-normal')
            if title_element:
                product_data['title'] = title_element.get_text(strip=True)

            # Price
            price_element = result.select_one('span.a-price > span.a-offscreen')
            if price_element:
                product_data['price'] = self._parse_price(price_element.get_text())

            # Original Price
            original_price_element = result.select_one('span.a-text-price > span.a-offscreen')
            if original_price_element:
                product_data['original_price'] = self._parse_price(original_price_element.get_text())

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
