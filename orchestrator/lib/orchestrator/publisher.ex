defmodule Orchestrator.Publisher do
  @moduledoc "Publica jobs no RabbitMQ"
  use GenServer

  alias AMQP.{Connection, Channel, Basic}

  def start_link(_opts) do
    GenServer.start_link(__MODULE__, %{}, name: __MODULE__)
  end

  def init(_state) do
    {:ok, conn} = Connection.open(System.get_env("RABBITMQ_URL"))
    {:ok, chan} = Channel.open(conn)
    # garantir exchange
    :ok = AMQP.Exchange.declare(chan, "jobs.exchange", :direct, durable: true)
    {:ok, %{chan: chan}}
  end

  def publish(job) do
    GenServer.call(__MODULE__, {:publish, job})
  end

  def handle_call({:publish, job}, _from, state) do
    payload = Jason.encode!(job)
    :ok = AMQP.Basic.publish(state.chan, "jobs.exchange", "jobs.#{job["job_type"] || "default"}", payload, persistent: true)
    {:reply, :ok, state}
  end
end
