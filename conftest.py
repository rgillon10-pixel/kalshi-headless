"""Make the substrate packages (core/, collection/, validation/) importable under pytest
regardless of how pytest is invoked. Repo-root conftest -> repo root on sys.path."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.resolve()))
