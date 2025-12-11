defmodule Orchestrator.Publisher do
  @moduledoc """
  Publica jobs de scraping no RabbitMQ.

  ## Exemplo de uso:

      Orchestrator.Publisher.publish_job(%{
        site_id: "mercadolivre",
        action: "search_product",
        payload: %{query: "iphone 15"}
      })
  """
  use GenServer
  require Logger

  @jobs_exchange "jobs.exchange"
  @jobs_routing_key "jobs.scraping"
  @results_exchange "results.exchange"

  # Client API

  def start_link(opts \\ []) do
    GenServer.start_link(__MODULE__, opts, name: __MODULE__)
  end

  @doc """
  Publica um job de scraping.

  ## Parâmetros
    - site_id: Identificador do site (ex: "mercadolivre", "amazon", "olx")
    - action: Ação a ser executada (ex: "search_product", "get_product_details")
    - payload: Dados específicos da ação

  ## Opções
    - priority: Prioridade do job ("low", "normal", "high") - default: "normal"
    - max_retries: Número máximo de tentativas - default: 3

  ## Retorno
    - {:ok, job_id} em caso de sucesso
    - {:error, reason} em caso de falha
  """
  @spec publish_job(map()) :: {:ok, String.t()} | {:error, term()}
  def publish_job(params) when is_map(params) do
    GenServer.call(__MODULE__, {:publish_job, params})
  end

  @doc """
  Lista os sites disponíveis para scraping.
  """
  @spec available_sites() :: [String.t()]
  def available_sites do
    # Preciso tornar isso dinamico futuramente
    ["mercadolivre", "amazon", "olx"]
  end

  # Server Callbacks

  @impl true
  def init(_opts) do
    case connect() do
      {:ok, state} ->
        {:ok, state}

      {:error, reason} ->
        Logger.error("Falha ao conectar ao RabbitMQ: #{inspect(reason)}")
        # Tenta reconectar após 5 segundos
        Process.send_after(self(), :reconnect, 5_000)
        {:ok, %{chan: nil, conn: nil}}
    end
  end

  @impl true
  def handle_call({:publish_job, params}, _from, %{chan: nil} = state) do
    {:reply, {:error, :not_connected}, state}
  end

  @impl true
  def handle_call({:publish_job, params}, _from, state) do
    job_id = generate_job_id()

    job = %{
      job_id: job_id,
      site_id: params[:site_id] || params["site_id"],
      action: params[:action] || params["action"] || "search_product",
      payload: params[:payload] || params["payload"] || %{},
      metadata: %{
        created_at: DateTime.utc_now() |> DateTime.to_iso8601(),
        priority: params[:priority] || params["priority"] || "normal",
        retry_count: 0,
        max_retries: params[:max_retries] || params["max_retries"] || 3
      }
    }

    case do_publish(state.chan, job) do
      :ok ->
        Logger.info("Job publicado: #{job_id} (site: #{job.site_id}, action: #{job.action})")
        {:reply, {:ok, job_id}, state}

      {:error, reason} = error ->
        Logger.error("Erro ao publicar job: #{inspect(reason)}")
        {:reply, error, state}
    end
  end

  @impl true
  def handle_info(:reconnect, state) do
    case connect() do
      {:ok, new_state} ->
        Logger.info("Reconectado ao RabbitMQ com sucesso")
        {:noreply, new_state}

      {:error, _reason} ->
        Process.send_after(self(), :reconnect, 5_000)
        {:noreply, state}
    end
  end

  @impl true
  def handle_info({:DOWN, _ref, :process, _pid, reason}, state) do
    Logger.warning("Conexão RabbitMQ perdida: #{inspect(reason)}")
    Process.send_after(self(), :reconnect, 1_000)
    {:noreply, %{state | chan: nil, conn: nil}}
  end

  # Private Functions

  defp connect do
    rabbitmq_url = System.get_env("RABBITMQ_URL")

    with {:ok, conn} <- AMQP.Connection.open(rabbitmq_url),
         {:ok, chan} <- AMQP.Channel.open(conn) do
      # Monitora a conexão para reconectar se cair
      Process.monitor(conn.pid)

      # Declara exchanges
      :ok = AMQP.Exchange.declare(chan, @jobs_exchange, :direct, durable: true)
      :ok = AMQP.Exchange.declare(chan, @results_exchange, :direct, durable: true)

      Logger.info("Conectado ao RabbitMQ")
      {:ok, %{chan: chan, conn: conn}}
    end
  end

  defp do_publish(channel, job) do
    payload = Jason.encode!(job)

    AMQP.Basic.publish(
      channel,
      @jobs_exchange,
      @jobs_routing_key,
      payload,
      persistent: true,
      content_type: "application/json"
    )
  end

  defp generate_job_id do
    UUID.uuid4()
  end
end
