.RECIPEPREFIX := >

.PHONY: install test coverage lint fmt typecheck build docker-build compose-up clean

install:
>python -m pip install -e ".[dev]"

test:
>python -m pytest

coverage:
>python -m pytest --cov=src --cov=cli --cov-report=term-missing

lint:
>python -m ruff check src cli tests
>python -m ruff format --check src cli tests

fmt:
>python -m ruff format src cli tests
>python -m ruff check --fix src cli tests

typecheck:
>python -m mypy src cli

build:
>python -m build

docker-build:
>docker build -t clouddeploy:latest .

compose-up:
>docker compose up -d

clean:
>python -B -c "import pathlib, shutil; [shutil.rmtree(p) for p in [pathlib.Path('build'), pathlib.Path('dist')] if p.exists()]"
>python -B -c "import pathlib; [p.unlink() for p in pathlib.Path('.').glob('*.egg-info')]"
>find . -name __pycache__ -type d -exec rm -rf {} +
