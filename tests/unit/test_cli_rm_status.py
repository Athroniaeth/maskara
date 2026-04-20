from typer.testing import CliRunner
from piighost.cli.main import app

runner = CliRunner()


def test_rm_help():
    result = runner.invoke(app, ["rm", "--help"])
    assert result.exit_code == 0
    assert "path" in result.output.lower()


def test_index_status_help():
    result = runner.invoke(app, ["index-status", "--help"])
    assert result.exit_code == 0


def test_index_force_flag():
    result = runner.invoke(app, ["index", "--help"])
    assert result.exit_code == 0
    assert "force" in result.output.lower()


def test_rm_exits_on_missing_vault(tmp_path):
    # Pass --vault pointing to a nonexistent directory; _resolve_vault raises VaultNotFound
    result = runner.invoke(
        app,
        ["rm", str(tmp_path / "doc.txt"), "--vault", str(tmp_path / "nonexistent")],
    )
    assert result.exit_code != 0
