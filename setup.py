"""Packaging configuration for the CloudDeploy deployment platform.

The canonical project metadata lives in ``pyproject.toml``; this module keeps
a thin setuptools shim for tooling that still expects a traditional setup.py.
"""

from pathlib import Path

from setuptools import find_packages, setup

HERE = Path(__file__).resolve().parent
README = (HERE / "README.md").read_text(encoding="utf-8")

setup(
    name="clouddeploy",
    version="1.4.0",
    description="Multi-cloud application deployment CLI and platform",
    long_description=README,
    long_description_content_type="text/markdown",
    author="CloudDeploy Contributors",
    license="MIT",
    packages=find_packages(include=("src", "src.*", "cli", "cli.*")),
    python_requires=">=3.11",
    install_requires=[
        "click>=8.1",
        "PyYAML>=6.0",
        "rich>=13.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0",
            "pytest-cov>=4.1",
            "mypy>=1.8",
            "ruff>=0.4",
            "types-PyYAML",
        ],
    },
    entry_points={
        "console_scripts": [
            "clouddeploy=cli.main:cli",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Build Tools",
        "Topic :: System :: Installation/Setup",
    ],
)
