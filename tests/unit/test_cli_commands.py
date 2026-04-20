from typer.testing import CliRunner
from piighost.cli.main import app

runner = CliRunner()


def test_index_help():
    result = runner.invoke(app, ["index", "--help"])
    assert result.exit_code == 0
    assert "path" in result.output.lower()


def test_query_help():
    result = runner.invoke(app, ["query", "--help"])
    assert result.exit_code == 0
    assert "text" in result.output.lower()


def test_vault_search_help():
    result = runner.invoke(app, ["vault", "search", "--help"])
    assert result.exit_code == 0


def test_serve_help():
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
