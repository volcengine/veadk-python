<p align="center">
    <img src="assets/images/logo.png" alt="Volcengine Agent Development Kit Logo" width="80%">
</p>

<p align="center">
    <h1 align="center">Volcengine Agent Development Kit</h1>
</p>

An open-source kit for agent development, integrated the powerful capabilities of Volcengine.

## Installation

We use `uv` to build this project ([how-to-install-uv](https://docs.astral.sh/uv/getting-started/installation/)).

```bash
git clone ... # clone repo first

cd veadk-python

uv venv --python 3.10

# only install necessary requirements
uv sync

# or, install extra requirements
# uv sync --extra database
# uv sync --extra eval
# uv sync --extra cli

# or, directly install all requirements
# uv sync --all-extras

# install veadk-python with editable mode
uv pip install -e .
```

## Configuration

We recommand you to create a `config.yaml` file in the root directory of your own project, `VeADK` is able to read it automatically.

You can refer to the [example config file](config.yaml.example) for more details.

## Have a try

Enjoy a minimal agent from VeADK:

```python
from veadk import Agent
import asyncio

agent = Agent()

res = asyncio.run(agent.run("hello!"))
print(res)
```

## Command line tools

### Fast deployment

Deploy your agent service by the following command:

```bash
vego deploy --access-key YOUR_ACCESS_KEY --secret-key YOUR_SECRET_KEY --name YOUR_SERVICE_NAME --path YOUR_PROJECT_PATH
```

## Contribution

Before making your contribution to our repository, please install and config the `pre-commit` linter first.

```bash
pip install pre-commit
pre-commit install
```

## License

This project is licensed under the [Apache 2.0 License](./LICENSE).
