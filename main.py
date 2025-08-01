import typer
from typing_extensions import Annotated
from enum import StrEnum


class ArchitectureChoice(StrEnum):
    threads = "threads"
    producer_consumer = "producer-consumer"


app = typer.Typer(help="Task processing system with different threading variants")

@app.command()
def run(
    architecture: Annotated[ArchitectureChoice, typer.Argument(help="Choose architecture: threads or producer-consumer")] = ArchitectureChoice.threads,
    producer_workers: Annotated[int, typer.Option("--producer-workers", help="Number of producer workers (only for producer-consumer)")] = 1,
    consumer_workers: Annotated[int, typer.Option("--consumer-workers", help="Number of consumer workers (only for producer-consumer)")] = 1,
    thread_workers: Annotated[int, typer.Option("--thread-workers", help="Number of thread workers (only for threads architecture)")] = 4
):
    """
    Run the task processing system with the specified architecture and configuration.

    Architectures:
    - threads: Use thread-based worker architecture
    - producer-consumer: Use producer-consumer architecture with configurable workers
    """

    if architecture == ArchitectureChoice.threads:
        typer.echo(f"Starting threads architecture with {thread_workers} workers...")
        from threads import main
        main(num_workers=thread_workers)

    elif architecture == ArchitectureChoice.producer_consumer:
        typer.echo(f"Starting producer-consumer architecture with {producer_workers} producer workers and {consumer_workers} consumer workers...")
        from producer_consumer import main
        main(num_producer_workers=producer_workers, num_consumer_workers=consumer_workers)

@app.command()
def list_variants():
    """List all available architectures with descriptions."""
    typer.echo("Available architectures:")
    typer.echo("  threads           - Thread-based worker architecture")
    typer.echo("  producer-consumer - Producer-consumer architecture with configurable workers")
    typer.echo("")
    typer.echo("Examples:")
    typer.echo("  python main.py run threads --thread-workers 8")
    typer.echo("  python main.py run producer-consumer --producer-workers 2 --consumer-workers 4")

if __name__ == "__main__":
    app()
