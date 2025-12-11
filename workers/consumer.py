"""
Generic Consumer - Consumidor genérico de jobs do RabbitMQ.

Este consumer:
1. Consome mensagens da fila de jobs
2. Identifica o site_id da mensagem
3. Despacha para o scraper apropriado via registry
4. Publica o resultado na fila de resultados
"""
import os
import sys
import json
import logging
from datetime import datetime
from typing import Optional

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("consumer")

# Importa o registry
from registry import get_registry


class JobConsumer:
    """Consumidor genérico de jobs com dispatch para scrapers."""

    def __init__(self, rabbitmq_url: str):
        self.rabbitmq_url = rabbitmq_url
        self.connection: Optional[pika.BlockingConnection] = None
        self.channel: Optional[BlockingChannel] = None

        # Configurações de exchanges e filas
        self.jobs_exchange = "jobs.exchange"
        self.jobs_queue = "jobs.scraping"
        self.jobs_routing_key = "jobs.scraping"

        self.results_exchange = "results.exchange"
        self.results_routing_key = "results.scraping"

        # Carrega o registry de scrapers
        self.registry = get_registry()
        logger.info(f"Scrapers disponíveis: {self.registry.list_sites()}")

    def connect(self) -> None:
        """Estabelece conexão com o RabbitMQ."""
        logger.info("Conectando ao RabbitMQ...")
        params = pika.URLParameters(self.rabbitmq_url)
        self.connection = pika.BlockingConnection(params)
        self.channel = self.connection.channel()

        # Declara exchanges
        self.channel.exchange_declare(
            exchange=self.jobs_exchange,
            exchange_type="direct",
            durable=True
        )
        self.channel.exchange_declare(
            exchange=self.results_exchange,
            exchange_type="direct",
            durable=True
        )

        # Declara e faz bind da fila de jobs
        self.channel.queue_declare(queue=self.jobs_queue, durable=True)
        self.channel.queue_bind(
            queue=self.jobs_queue,
            exchange=self.jobs_exchange,
            routing_key=self.jobs_routing_key
        )

        # Configura QoS (prefetch)
        self.channel.basic_qos(prefetch_count=1)

        logger.info("Conexão estabelecida com sucesso")

    def process_job(self, body: bytes) -> dict:
        """
        Processa um job recebido.

        Args:
            body: Corpo da mensagem (JSON bytes)

        Returns:
            Resultado do processamento
        """
        job = json.loads(body)
        job_id = job.get("job_id", "unknown")
        site_id = job.get("site_id")
        action = job.get("action", "search_product")
        payload = job.get("payload", {})

        logger.info(f"[Job {job_id}] Processando: site={site_id}, action={action}")

        # Valida campos obrigatórios
        if not site_id:
            return self._create_error_result(
                job_id=job_id,
                site_id=site_id,
                error="Campo 'site_id' é obrigatório"
            )

        # Busca o scraper no registry
        scraper = self.registry.get(site_id)
        if not scraper:
            return self._create_error_result(
                job_id=job_id,
                site_id=site_id,
                error=f"Scraper não encontrado para site_id '{site_id}'",
                extra={"available_sites": self.registry.list_sites()}
            )

        # Executa a ação no scraper
        result = scraper.execute(action, payload)

        # Monta resposta
        return {
            "job_id": job_id,
            "site_id": site_id,
            "action": action,
            "status": result.status,
            "data": result.data,
            "error": result.error,
            "metadata": {
                **result.metadata,
                "processed_at": datetime.utcnow().isoformat()
            }
        }

    def _create_error_result(
        self,
        job_id: str,
        site_id: Optional[str],
        error: str,
        extra: dict = None
    ) -> dict:
        """Cria um resultado de erro padronizado."""
        return {
            "job_id": job_id,
            "site_id": site_id,
            "status": "failed",
            "data": extra or {},
            "error": error,
            "metadata": {
                "processed_at": datetime.utcnow().isoformat()
            }
        }

    def publish_result(self, result: dict) -> None:
        """Publica resultado na fila de resultados."""
        self.channel.basic_publish(
            exchange=self.results_exchange,
            routing_key=self.results_routing_key,
            body=json.dumps(result),
            properties=pika.BasicProperties(
                delivery_mode=2,  # persistent
                content_type="application/json"
            )
        )
        logger.info(f"[Job {result.get('job_id')}] Resultado publicado")

    def on_message(
        self,
        channel: BlockingChannel,
        method: Basic.Deliver,
        properties: BasicProperties,
        body: bytes
    ) -> None:
        """Callback executado ao receber uma mensagem."""
        job_id = "unknown"
        try:
            # Processa o job
            result = self.process_job(body)
            job_id = result.get("job_id", job_id)

            # Publica resultado
            self.publish_result(result)

            # Confirma processamento
            channel.basic_ack(delivery_tag=method.delivery_tag)
            logger.info(f"[Job {job_id}] Concluído com status: {result.get('status')}")

        except json.JSONDecodeError as e:
            logger.error(f"Erro ao decodificar JSON: {e}")
            # Rejeita mensagem malformada sem requeue
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        except Exception as e:
            logger.exception(f"[Job {job_id}] Erro não esperado: {e}")

            # Publica erro
            error_result = self._create_error_result(
                job_id=job_id,
                site_id=None,
                error=str(e)
            )
            self.publish_result(error_result)

            # Rejeita sem requeue (evita loop infinito)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def start(self) -> None:
        """Inicia o consumer."""
        self.connect()

        logger.info(f"Aguardando jobs na fila '{self.jobs_queue}'...")
        logger.info("Pressione CTRL+C para sair")

        self.channel.basic_consume(
            queue=self.jobs_queue,
            on_message_callback=self.on_message
        )

        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("Encerrando consumer...")
            self.channel.stop_consuming()
        finally:
            if self.connection:
                self.connection.close()


def main():
    """Ponto de entrada do consumer."""
    rabbitmq_url = os.environ.get(
        "RABBITMQ_URL",
        "amqp://guest:guest@localhost:5672"
    )

    consumer = JobConsumer(rabbitmq_url)
    consumer.start()


if __name__ == "__main__":
    main()
