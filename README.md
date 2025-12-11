# MultiScrap

Sistema distribuído de web scraping com orquestração em Elixir e workers em Python.

## Arquitetura

O sistema é composto por três camadas principais:

1. **Orchestrator (Elixir/Phoenix)** - Gerencia jobs, publica tarefas e consome resultados
2. **Message Broker (RabbitMQ)** - Comunicação assíncrona entre componentes
3. **Workers (Python)** - Executam scraping com suporte a múltiplos sites via plugin system

### Fluxo Principal

```mermaid
flowchart TB
    subgraph Orchestrator["Orchestrator (Elixir)"]
        API[API/LiveView]
        Publisher[Publisher GenServer]
        Consumer[Broadway Consumer]
        Redis[(Redis Cache)]
    end

    subgraph RabbitMQ["RabbitMQ"]
        JobsExchange[jobs.exchange]
        JobsQueue[jobs.scraping]
        ResultsExchange[results.exchange]
        ResultsQueue[results.scraping]
    end

    subgraph Workers["Python Workers"]
        GenericConsumer[Generic Consumer]
        Registry[Scraper Registry]

        subgraph Scrapers["Site Scrapers"]
            ML[mercadolivre.py]
            AMZ[amazon.py]
            OLX[olx.py]
            Custom[custom_site.py]
        end
    end

    %% Fluxo de Jobs
    API -->|1. Cria Job| Publisher
    Publisher -->|2. Publica| JobsExchange
    JobsExchange -->|3. Roteia| JobsQueue
    JobsQueue -->|4. Consome| GenericConsumer

    %% Dispatch para Scrapers
    GenericConsumer -->|5. Identifica site_id| Registry
    Registry -->|6. Despacha| Scrapers

    %% Retorno de Resultados
    Scrapers -->|7. Resultado| GenericConsumer
    GenericConsumer -->|8. Publica resultado| ResultsExchange
    ResultsExchange -->|9. Roteia| ResultsQueue
    ResultsQueue -->|10. Consome| Consumer

    %% Persistência
    Consumer -->|11. Persiste| Redis
    Publisher -.->|Estado do Job| Redis
```

### Fluxo de Mensagens Detalhado

```mermaid
sequenceDiagram
    autonumber
    participant Client as Cliente
    participant Orch as Orchestrator
    participant RMQ as RabbitMQ
    participant Worker as Python Worker
    participant Scraper as Site Scraper
    participant Redis as Redis

    Client->>Orch: POST /api/jobs {site_id, url, params}
    Orch->>Redis: SET job:{id} = pending
    Orch->>RMQ: Publish to jobs.exchange

    RMQ->>Worker: Consume from jobs.scraping
    Worker->>Worker: Identify site_id
    Worker->>Scraper: dispatch(site_id, payload)

    alt Scraping Success
        Scraper-->>Worker: {status: ok, data: {...}}
        Worker->>RMQ: Publish to results.exchange
        RMQ->>Orch: Consume from results.scraping
        Orch->>Redis: SET job:{id} = completed
        Orch-->>Client: WebSocket/Poll: Job completed
    else Scraping Failed
        Scraper-->>Worker: {status: error, reason: "..."}
        Worker->>RMQ: Publish error to results.exchange
        RMQ->>Orch: Consume error
        Orch->>Redis: SET job:{id} = failed
        Orch-->>Client: WebSocket/Poll: Job failed
    end
```

### Estrutura do Projeto

```
multiscrap/
├── orchestrator/           # Aplicação Elixir/Phoenix
│   ├── lib/
│   │   ├── orchestrator/
│   │   │   ├── application.ex
│   │   │   ├── publisher.ex      # Publica jobs no RabbitMQ
│   │   │   ├── consumer.ex       # Broadway consumer (resultados)
│   │   │   ├── job_supervisor.ex
│   │   │   └── redis.ex          # Cliente Redis
│   │   └── orchestrator_web/
│   │       ├── controllers/
│   │       └── live/             # LiveView para dashboard
│   └── config/
│
├── workers/                # Workers Python
│   ├── consumer.py         # Consumer genérico
│   ├── registry.py         # Registry de scrapers
│   ├── base_scraper.py     # Classe base para scrapers
│   ├── scrapers/           # Scrapers específicos por site
│   │   ├── __init__.py
│   │   ├── mercadolivre.py
│   │   ├── amazon.py
│   │   └── olx.py
│   └── requirements.txt
│
├── docker-compose.yml
├── .env
└── README.md
```

## Schema de Mensagens

### Job Request (Orchestrator → Worker)

```json
{
  "job_id": "uuid-v4",
  "site_id": "mercadolivre",
  "action": "search_product",
  "payload": {
    "url": "https://...",
    "search_term": "iphone 15",
    "filters": {}
  },
  "metadata": {
    "created_at": "2024-01-01T00:00:00Z",
    "priority": "normal",
    "retry_count": 0,
    "max_retries": 3
  }
}
```

### Job Result (Worker → Orchestrator)

```json
{
  "job_id": "uuid-v4",
  "site_id": "mercadolivre",
  "status": "completed",
  "data": {
    "products": [...],
    "total_found": 150
  },
  "metadata": {
    "started_at": "2024-01-01T00:00:01Z",
    "completed_at": "2024-01-01T00:00:05Z",
    "duration_ms": 4000
  }
}
```

## Como Adicionar um Novo Scraper

1. Crie um arquivo em `workers/scrapers/nome_do_site.py`:

```python
from base_scraper import BaseScraper, ScraperResult

class NomeDoSiteScraper(BaseScraper):
    site_id = "nome_do_site"

    def search_product(self, payload: dict) -> ScraperResult:
        # Implementar lógica de scraping
        return ScraperResult(
            status="completed",
            data={"products": [...]}
        )

    def get_product_details(self, payload: dict) -> ScraperResult:
        # Outra ação disponível
        pass
```

2. Registre no `workers/scrapers/__init__.py`:

```python
from .nome_do_site import NomeDoSiteScraper
```

3. O scraper será automaticamente descoberto pelo registry.

## Setup Local

### Pré-requisitos

- Elixir 1.15+ / OTP 27
- Python 3.11+
- Docker & Docker Compose

### Executar

```bash
# Subir infraestrutura
docker-compose up -d rabbitmq redis

# Orchestrator (terminal 1)
cd orchestrator
mix deps.get
mix phx.server

# Worker Python (terminal 2)
cd workers
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python consumer.py
```

## Configuração

### Variáveis de Ambiente

| Variável | Descrição | Default |
|----------|-----------|---------|
| `RABBITMQ_URL` | URL de conexão AMQP | `amqp://guest:guest@localhost:5672` |
| `REDIS_URL` | URL de conexão Redis | `redis://localhost:6379` |
| `PORT` | Porta do servidor Phoenix | `4000` |

## Roadmap

- [x] Setup inicial do projeto
- [x] Configuração RabbitMQ e Redis
- [x] Publisher básico (Elixir)
- [ ] Consumer genérico (Python)
- [ ] Sistema de registry de scrapers
- [ ] Scrapers de exemplo (MercadoLivre, Amazon, OLX)
- [ ] Broadway consumer para resultados
- [ ] Redis para estado dos jobs
- [ ] API REST para submissão de jobs
- [ ] Dashboard LiveView
- [ ] Sistema de retry com backoff
- [ ] Métricas e observabilidade
