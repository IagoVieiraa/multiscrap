"""
Scraper Registry - Sistema de registro e descoberta automática de scrapers.

O registry descobre automaticamente todos os scrapers no diretório `scrapers/`
e os registra pelo seu `site_id`.
"""
import importlib
import pkgutil
import logging
from typing import Optional, Type
from base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class ScraperRegistry:
    """
    Registry central para todos os scrapers disponíveis.

    Uso:
        registry = ScraperRegistry()
        registry.discover()  # Carrega scrapers do diretório scrapers/

        scraper = registry.get("mercadolivre")
        result = scraper.execute("search_product", {"query": "iphone"})
    """

    def __init__(self):
        self._scrapers: dict[str, Type[BaseScraper]] = {}

    def register(self, scraper_class: Type[BaseScraper]) -> None:
        """Registra um scraper manualmente."""
        if not scraper_class.site_id:
            raise ValueError(f"Scraper {scraper_class.__name__} não tem site_id definido")

        if scraper_class.site_id in self._scrapers:
            logger.warning(
                f"Scraper para '{scraper_class.site_id}' já existe, "
                f"substituindo {self._scrapers[scraper_class.site_id].__name__} "
                f"por {scraper_class.__name__}"
            )

        self._scrapers[scraper_class.site_id] = scraper_class
        logger.info(f"Scraper registrado: {scraper_class.site_id} -> {scraper_class.__name__}")

    def discover(self, package_name: str = "scrapers") -> int:
        """
        Descobre e registra automaticamente todos os scrapers no pacote.

        Args:
            package_name: Nome do pacote onde procurar scrapers

        Returns:
            Número de scrapers descobertos
        """
        count = 0
        try:
            package = importlib.import_module(package_name)
        except ImportError as e:
            logger.error(f"Não foi possível importar pacote '{package_name}': {e}")
            return 0

        # Itera sobre todos os módulos no pacote
        for importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
            if modname.startswith('_'):
                continue

            try:
                module = importlib.import_module(f"{package_name}.{modname}")

                # Procura classes que herdam de BaseScraper
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)

                    # Verifica se é uma classe, herda de BaseScraper e não é a própria BaseScraper
                    if (isinstance(attr, type)
                        and issubclass(attr, BaseScraper)
                        and attr is not BaseScraper
                        and attr.site_id is not None):

                        self.register(attr)
                        count += 1

            except Exception as e:
                logger.exception(f"Erro ao carregar módulo {modname}: {e}")

        logger.info(f"Descoberta completa: {count} scraper(s) registrado(s)")
        return count

    def get(self, site_id: str) -> Optional[BaseScraper]:
        """
        Obtém uma instância do scraper para o site_id.

        Args:
            site_id: Identificador do site

        Returns:
            Instância do scraper ou None se não encontrado
        """
        scraper_class = self._scrapers.get(site_id)
        if scraper_class:
            return scraper_class()
        return None

    def has(self, site_id: str) -> bool:
        """Verifica se existe um scraper para o site_id."""
        return site_id in self._scrapers

    def list_sites(self) -> list[str]:
        """Retorna lista de todos os site_ids disponíveis."""
        return list(self._scrapers.keys())

    def get_scraper_info(self, site_id: str) -> Optional[dict]:
        """Retorna informações sobre um scraper específico."""
        scraper = self.get(site_id)
        if not scraper:
            return None

        return {
            "site_id": site_id,
            "class_name": scraper.__class__.__name__,
            "available_actions": scraper.get_available_actions()
        }

    def list_all_info(self) -> list[dict]:
        """Retorna informações sobre todos os scrapers registrados."""
        return [
            self.get_scraper_info(site_id)
            for site_id in self._scrapers
        ]


# Instância global do registry (singleton pattern)
_registry: Optional[ScraperRegistry] = None


def get_registry() -> ScraperRegistry:
    """Obtém a instância global do registry, criando se necessário."""
    global _registry
    if _registry is None:
        _registry = ScraperRegistry()
        _registry.discover()
    return _registry
