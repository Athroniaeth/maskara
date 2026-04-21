"""`piighost docker` — initialisation et état de l'installation Docker."""
from __future__ import annotations

import base64
import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path

import typer

app = typer.Typer(
    name="docker",
    help="Gestion de l'installation Docker de piighost.",
    no_args_is_help=True,
)


def _secret_dir() -> Path:
    return Path("docker/secrets")


def _refuse_overwrite(path: Path) -> None:
    if path.exists():
        typer.echo(
            f"error: {path} exists. refuse to overwrite — "
            f"delete it manually first if you really want to regenerate.",
            err=True,
        )
        raise typer.Exit(code=2)


def _write_secret(path: Path, content: str) -> None:
    _refuse_overwrite(path)
    path.write_text(content, encoding="utf-8")
    if os.name == "posix":
        os.chmod(path, 0o600)


@app.command("init")
def init(
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Ne pas demander de confirmation."
    ),
) -> None:
    """Génère les secrets et le fichier .env pour une première installation."""
    sdir = _secret_dir()
    sdir.mkdir(parents=True, exist_ok=True)

    if not yes:
        typer.confirm(
            "Cela va générer de nouveaux secrets. Continuer ?", abort=True
        )

    # Vault key: 32 random bytes → base64url (no padding)
    vault_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    _write_secret(sdir / "vault-key.txt", vault_key + "\n")

    # Age recipient + key pair — requires `age-keygen` on PATH
    if shutil.which("age-keygen"):
        key_path = sdir / "age.key"
        _refuse_overwrite(key_path)
        subprocess.run(
            ["age-keygen", "-o", str(key_path)], check=True, capture_output=True
        )
        if os.name == "posix":
            os.chmod(key_path, 0o600)
        pub = subprocess.run(
            ["age-keygen", "-y", str(key_path)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        _write_secret(sdir / "age-recipient.txt", pub + "\n")
    else:
        typer.echo(
            "warning: `age-keygen` not found on PATH. Skipping age key "
            "generation — backups will fail until you provide "
            "docker/secrets/age-recipient.txt manually.",
            err=True,
        )

    # Bearer tokens: empty file — operator adds via `piighost token create`
    (sdir / "bearer-tokens.txt").touch()
    if os.name == "posix":
        os.chmod(sdir / "bearer-tokens.txt", 0o600)

    # .env from .env.example
    env_example = Path(".env.example")
    env_file = Path(".env")
    if env_example.exists() and not env_file.exists():
        env_file.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
        typer.echo(f"created {env_file} from template")

    typer.echo("piighost docker init: done.")


@app.command("status")
def status() -> None:
    """Affiche l'état des conteneurs, dernière sauvegarde, mises à jour disponibles."""
    try:
        out = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        typer.echo(f"docker compose unavailable: {exc}", err=True)
        raise typer.Exit(code=1)

    services = [json.loads(line) for line in out.splitlines() if line.strip()]
    for s in services:
        typer.echo(f"  {s.get('Service', '?'):20s}  {s.get('State', '?')}")

    backups = sorted(Path("backups").glob("piighost-*.tar.age"))
    if backups:
        typer.echo(f"last backup: {backups[-1].name}")
    else:
        typer.echo("last backup: none")

    uaf = Path("/var/lib/piighost/update-available.json")
    if uaf.exists():
        info = json.loads(uaf.read_text(encoding="utf-8"))
        typer.echo(
            f"update available: {info['tag']} {info['installed']} -> {info['latest']}"
        )
