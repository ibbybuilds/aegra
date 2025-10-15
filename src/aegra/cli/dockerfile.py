from pathlib import Path

import click


@click.command()
def dockerfile():
    """Generate Dockerfile."""
    path = Path(__file__).parent.absolute() / "tmpl.Dockerfile"
    with path.open("r") as f:
        content = f.read()

    with (Path.cwd() / "Dockerfile").open("w") as f:
        f.write(content)

    click.echo("Generated Dockerfile.")
