"""
Scrapers Package - Contém todos os scrapers específicos por site.

Para adicionar um novo scraper:
1. Crie um arquivo nome_do_site.py neste diretório
2. Importe a classe aqui
3. O registry irá descobri-lo automaticamente
"""
from .mercadolivre import MercadoLivreScraper
from .amazon import AmazonScraper
from .olx import OLXScraper

__all__ = [
    "MercadoLivreScraper",
    "AmazonScraper",
    "OLXScraper",
]
