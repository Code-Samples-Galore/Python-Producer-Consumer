import typer
from typing_extensions import Annotated
from enum import Enum

class VariantChoice(str, Enum):
    single = "single"
    consumer_multi = "consumer-multi"
    producer_multi = "producer-multi"
    both_multi = "both-multi"
    only_workers = "only-workers"

app = typer.Typer(help="Task processing system with different threading variants")

@app.command()
def run(
    variant: Annotated[VariantChoice, typer.Argument(help="Choose which variant to run")] = VariantChoice.single
):
    """
    Run the task processing system with the specified variant.

    Variants:
    - single: Single-threaded producer and consumer
    - consumer-multi: Multi-threaded consumer, single-threaded producer
    - producer-multi: Multi-threaded producer, single-threaded consumer
    - both-multi: Multi-threaded producer and consumer
    - only-workers: Workers process tasks from a pre-populated queue
    """

    typer.echo(f"Starting {variant.value} variant...")

    if variant == VariantChoice.single:
        from single_threaded import main
        main()
    elif variant == VariantChoice.consumer_multi:
        from consumer_multi_threaded import main
        main()
    elif variant == VariantChoice.producer_multi:
        from producer_multi_threaded import main
        main()
    elif variant == VariantChoice.both_multi:
        from multi_threaded import main
        main()
    elif variant == VariantChoice.only_workers:
        from only_workers import main
        main()

@app.command()
def list_variants():
    """List all available variants with descriptions."""
    typer.echo("Available variants:")
    typer.echo("  single           - Single-threaded producer and consumer")
    typer.echo("  consumer-multi   - Multi-threaded consumer, single-threaded producer")
    typer.echo("  producer-multi   - Multi-threaded producer, single-threaded consumer")
    typer.echo("  both-multi       - Multi-threaded producer and consumer")
    typer.echo("  only-workers     - Workers process tasks from a pre-populated queue")

if __name__ == "__main__":
    app()
