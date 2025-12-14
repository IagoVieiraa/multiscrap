"""
Base Scraper - Classe base para todos os scrapers do sistema.

Para criar um novo scraper:
1. Herde de BaseScraper
2. Defina site_id como atributo de classe
3. Implemente os métodos de ação (search_product, get_details, etc)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ScraperResult:
    """Resultado padronizado de uma operação de scraping."""
    status: str  # "completed", "failed", "partial"
    data: dict = field(default_factory=dict)
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata
        }


class BaseScraper(ABC):
    """
    Classe base abstrata para scrapers.

    Cada scraper deve:
    - Definir `site_id` como atributo de classe
    - Implementar métodos para cada ação suportada
    """

    site_id: str = None  # Deve ser sobrescrito nas subclasses

    def __init__(self):
        if not self.site_id:
            raise ValueError(f"{self.__class__.__name__} deve definir site_id")
        self.logger = logging.getLogger(f"scraper.{self.site_id}")

    def execute(self, action: str, payload: dict) -> ScraperResult:
        """
        Executa uma ação no scraper.

        Args:
            action: Nome do método a ser chamado (ex: "search_product")
            payload: Dados necessários para a ação

        Returns:
            ScraperResult com o resultado da operação
        """
        started_at = datetime.now(datetime.timezone.utc)

        # Verifica se a ação existe
        if not hasattr(self, action):
            return ScraperResult(
                status="failed",
                error=f"Ação '{action}' não suportada pelo scraper '{self.site_id}'",
                metadata={"available_actions": self.get_available_actions()}
            )

        method = getattr(self, action)
        if not callable(method):
            return ScraperResult(
                status="failed",
                error=f"'{action}' não é um método válido"
            )

        try:
            self.logger.info(f"Executando {action} com payload: {payload}")
            result = method(payload)

            # Adiciona metadata de tempo
            completed_at = datetime.now(datetime.timezone.utc)
            result.metadata.update({
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration_ms": int((completed_at - started_at).total_seconds() * 1000)
            })

            return result

        except Exception as e:
            self.logger.exception(f"Erro ao executar {action}")
            return ScraperResult(
                status="failed",
                error=str(e),
                metadata={
                    "started_at": started_at.isoformat(),
                    "completed_at": datetime.utcnow().isoformat()
                }
            )

    def get_available_actions(self) -> list[str]:
        """Retorna lista de ações disponíveis neste scraper."""
        # Retorna métodos públicos que não começam com _ e não são herdados de object
        return [
            method for method in dir(self)
            if not method.startswith('_')
            and callable(getattr(self, method))
            and method not in ('execute', 'get_available_actions', 'to_dict')
        ]

    def __repr__(self):
        return f"<{self.__class__.__name__} site_id='{self.site_id}'>"
