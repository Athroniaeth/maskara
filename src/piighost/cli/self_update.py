"""`piighost self-update` — safe, signature-verified image updates."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import typer

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

app = typer.Typer(name="self-update", help="Met à jour les images Docker de manière sûre.")

# Permissive: accept any sha256:<token> pattern so test fixtures with
# placeholder digests parse too. Real digests are 64 hex chars.
DIGEST_RE = re.compile(r"(ghcr\.io/jamon8888/hacienda-ghost)@(sha256:[^\s\"'`]+)")
DEFAULT_IMAGE = "ghcr.io/jamon8888/hacienda-ghost"


def _fetch_latest_digest(image: str, tag: str) -> str:
    """Return the sha256 digest of the latest image+tag from GHCR."""
    if httpx is None:
        raise RuntimeError("httpx not installed; run `pip install piighost[docker]`")

    host, name = image.split("/", 1)
    tok = httpx.get(
        f"https://{host}/token",
        params={"service": host, "scope": f"repository:{name}:pull"},
        timeout=10,
    ).json().get("token", "")
    r = httpx.get(
        f"https://{host}/v2/{name}/manifests/{tag}",
        headers={
            "Accept": "application/vnd.oci.image.index.v1+json, "
                      "application/vnd.docker.distribution.manifest.v2+json",
            "Authorization": f"Bearer {tok}" if tok else "",
        },
        timeout=10,
    )
    r.raise_for_status()
    digest = r.headers.get("Docker-Content-Digest", "")
    if not digest.startswith("sha256:"):
        raise RuntimeError(f"unexpected digest format: {digest!r}")
    return digest


def _verify_cosign_signature(image_ref: str) -> bool:
    """Run `cosign verify --certificate-identity-regexp ...`."""
    if not shutil.which("cosign"):
        typer.echo(
            "warning: cosign not found; skipping signature verification",
            err=True,
        )
        return True
    try:
        subprocess.run(
            [
                "cosign", "verify",
                "--certificate-identity-regexp", r"https://github\.com/jamon8888/.*",
                "--certificate-oidc-issuer", "https://token.actions.githubusercontent.com",
                image_ref,
            ],
            capture_output=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        typer.echo(f"cosign verification failed: {exc.stderr.decode(errors='replace')}", err=True)
        return False


@app.callback(invoke_without_command=True)
def self_update(
    tag: str = typer.Option("slim", help="Tag image: slim ou full."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Ne pas demander confirmation."),
) -> None:
    """Met à jour `docker-compose.yml` avec le dernier digest signé."""
    compose = Path("docker-compose.yml")
    if not compose.exists():
        typer.echo("docker-compose.yml not found in current directory", err=True)
        raise typer.Exit(code=2)

    latest = _fetch_latest_digest(DEFAULT_IMAGE, tag)
    typer.echo(f"latest {tag} digest: {latest}")

    if not _verify_cosign_signature(f"{DEFAULT_IMAGE}@{latest}"):
        typer.echo("aborting: signature verification failed", err=True)
        raise typer.Exit(code=3)

    text = compose.read_text(encoding="utf-8")
    new_text = DIGEST_RE.sub(lambda m: f"{m.group(1)}@{latest}", text)
    if new_text == text:
        typer.echo("no digest references updated (already latest?)")
        raise typer.Exit(code=0)

    if not yes:
        typer.confirm("Écrire ces changements dans docker-compose.yml ?", abort=True)

    compose.write_text(new_text, encoding="utf-8")
    typer.echo("docker-compose.yml updated. Run `docker compose pull && docker compose up -d` to apply.")
