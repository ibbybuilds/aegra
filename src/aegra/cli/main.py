import click

from aegra.cli.dockerfile import dockerfile
from aegra.cli.migrate import migrate
from aegra.cli.server import dev, serve


@click.group()
def cli():
    """
    Aegra CLI: Open Source LangGraph Platform
    """
    pass


cli.add_command(serve)
cli.add_command(dev)
cli.add_command(migrate)
cli.add_command(dockerfile)

if __name__ == "__main__":
    cli()
