defmodule Orchestrator.JobSupervisor do
  use Supervisor

  def start_link(_), do: Supervisor.start_link(__MODULE__, :ok, name: __MODULE__)

  def init(:ok) do
    children = [
      {Orchestrator.Publisher, []}
      # outros processos: consumer, telemetry, etc
    ]
    Supervisor.init(children, strategy: :one_for_one)
  end
end
