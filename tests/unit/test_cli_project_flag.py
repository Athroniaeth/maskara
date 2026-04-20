from typer.testing import CliRunner

from piighost.cli.main import app

runner = CliRunner()


def test_anonymize_has_project_flag():
    result = runner.invoke(app, ["anonymize", "--help"])
    assert result.exit_code == 0
    assert "--project" in result.output


def test_query_has_project_flag():
    result = runner.invoke(app, ["query", "--help"])
    assert result.exit_code == 0
    assert "--project" in result.output


def test_index_has_project_flag():
    result = runner.invoke(app, ["index", "--help"])
    assert result.exit_code == 0
    assert "--project" in result.output


def test_vault_list_has_project_flag():
    result = runner.invoke(app, ["vault", "list", "--help"])
    assert result.exit_code == 0
    assert "--project" in result.output


def test_rm_has_project_flag():
    result = runner.invoke(app, ["rm", "--help"])
    assert result.exit_code == 0
    assert "--project" in result.output


def test_index_status_has_project_flag():
    result = runner.invoke(app, ["index-status", "--help"])
    assert result.exit_code == 0
    assert "--project" in result.output


def test_rehydrate_has_project_flag():
    result = runner.invoke(app, ["rehydrate", "--help"])
    assert result.exit_code == 0
    assert "--project" in result.output


def test_projects_list_command_exists():
    result = runner.invoke(app, ["projects", "list", "--help"])
    assert result.exit_code == 0


def test_projects_create_command_exists():
    result = runner.invoke(app, ["projects", "create", "--help"])
    assert result.exit_code == 0
    assert "name" in result.output.lower()


def test_projects_delete_command_exists():
    result = runner.invoke(app, ["projects", "delete", "--help"])
    assert result.exit_code == 0
