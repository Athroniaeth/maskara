from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastmcp import FastMCP

from piighost.service.config import ServiceConfig
from piighost.service.core import PIIGhostService
from piighost.service.models import VaultEntryModel


def _indexing_available() -> bool:
    import importlib.util
    return importlib.util.find_spec("sentence_transformers") is not None


def _last_update_iso(files) -> str | None:
    """Return the most recent ``indexed_at`` as an ISO 8601 UTC string, or None.

    ``indexed_at`` is a Unix timestamp (seconds).  Skills compare this field
    against ``now - 10 min`` on network drives, so a stable string format with
    timezone marker is required.  Returns ``None`` (→ JSON ``null``) when no
    files are indexed yet, so the ``/status`` skill can render "never".
    """
    from datetime import datetime, timezone
    if not files:
        return None
    latest = max(f.indexed_at for f in files)
    return datetime.fromtimestamp(latest, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


async def build_mcp(vault_dir: Path, config: ServiceConfig | None = None) -> tuple[FastMCP, PIIGhostService]:
    if config is None:
        config = ServiceConfig()
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    mcp = FastMCP("piighost", "GDPR-compliant PII anonymization and document retrieval")

    @mcp.tool(description="Anonymize text, replacing PII with opaque tokens")
    async def anonymize_text(text: str, doc_id: str = "", project: str = "default") -> dict:
        result = await svc.anonymize(text, doc_id=doc_id or None, project=project)
        return result.model_dump()

    @mcp.tool(description="Rehydrate anonymized text back to original PII")
    async def rehydrate_text(text: str, project: str = "default") -> dict:
        result = await svc.rehydrate(text, project=project)
        return result.model_dump()

    if _indexing_available():
        @mcp.tool(description="Index a file or directory into the retrieval store")
        async def index_path(
            path: str,
            recursive: bool = True,
            force: bool = False,
            project: str = "",
        ) -> dict:
            project_arg = project if project else None
            report = await svc.index_path(
                Path(path), recursive=recursive, force=force, project=project_arg
            )
            return report.model_dump()

        @mcp.tool(description="Hybrid BM25+vector search over indexed documents")
        async def query(
            text: str,
            k: int = 5,
            project: str = "default",
            filter_prefix: str = "",
            filter_doc_ids: list[str] | None = None,
            rerank: bool = False,
            top_n: int = 20,
        ) -> dict:
            from piighost.indexer.filters import QueryFilter
            qfilter = None
            if filter_prefix or filter_doc_ids:
                qfilter = QueryFilter(
                    file_path_prefix=filter_prefix or None,
                    doc_ids=tuple(filter_doc_ids or ()),
                )
            result = await svc.query(
                text, k=k, project=project, filter=qfilter, rerank=rerank, top_n=top_n
            )
            return result.model_dump()

    @mcp.tool(description="Full-text search in the PII vault by original value")
    async def vault_search(
        q: str, reveal: bool = False, project: str = "default"
    ) -> list[dict]:
        entries = await svc.vault_search(q, reveal=reveal, project=project)
        return [e.model_dump() for e in entries]

    @mcp.tool(description="List vault entries with optional label filter")
    async def vault_list(
        label: str = "",
        limit: int = 100,
        offset: int = 0,
        reveal: bool = False,
        project: str = "default",
    ) -> list[dict]:
        page = await svc.vault_list(
            label=label or None,
            limit=limit,
            offset=offset,
            reveal=reveal,
            project=project,
        )
        return [e.model_dump(exclude_none=False) for e in page.entries]

    @mcp.tool(description="Retrieve a single vault entry by token")
    async def vault_get(
        token: str, reveal: bool = False, project: str = "default"
    ) -> dict | None:
        entry = await svc.vault_show(token, reveal=reveal, project=project)
        return entry.model_dump() if entry is not None else None

    @mcp.tool(description="Return vault statistics (total entries, by label)")
    async def vault_stats(project: str = "default") -> dict:
        stats = await svc.vault_stats(project=project)
        return stats.model_dump()

    @mcp.tool(description="List all projects")
    async def list_projects() -> list[dict]:
        projects = await svc.list_projects()
        return [
            {
                "name": p.name,
                "description": p.description,
                "created_at": p.created_at,
                "last_accessed_at": p.last_accessed_at,
            }
            for p in projects
        ]

    @mcp.tool(description="Create a new project")
    async def create_project(name: str, description: str = "") -> dict:
        info = await svc.create_project(name, description=description)
        return {
            "name": info.name,
            "description": info.description,
            "created_at": info.created_at,
        }

    @mcp.tool(description="Delete a project (refuses if non-empty unless force=True)")
    async def delete_project(name: str, force: bool = False) -> dict:
        deleted = await svc.delete_project(name, force=force)
        return {"deleted": deleted, "name": name}

    @mcp.tool(description="Check whether the piighost daemon is running")
    async def daemon_status() -> dict:
        from piighost.daemon.lifecycle import status
        hs = status(vault_dir)
        if hs is None:
            return {"running": False}
        return {"running": True, "pid": hs.pid, "port": hs.port}

    @mcp.tool(description="Stop the piighost daemon gracefully")
    async def daemon_stop() -> dict:
        from piighost.daemon.lifecycle import stop_daemon
        stopped = stop_daemon(vault_dir)
        return {"stopped": stopped}

    from piighost.mcp.folder import project_name_for_folder

    @mcp.tool(
        description=(
            "Resolve the Cowork active folder to its piighost project name. "
            "Deterministic: same folder always maps to the same project. "
            "Use this in every hacienda skill before calling index_path or query."
        )
    )
    async def resolve_project_for_folder(folder: str) -> dict:
        project = project_name_for_folder(Path(folder))
        return {"folder": folder, "project": project}

    from piighost.mcp.audit import SessionAudit

    def _audit_for(session_id: str) -> SessionAudit:
        root = Path(os.environ.get("HACIENDA_DATA_DIR", Path.home() / ".hacienda"))
        return SessionAudit(root=root, session_id=session_id)

    @mcp.tool(
        description=(
            "Append an event to the current Cowork session's audit log. "
            "Payload MUST use placeholders/tokens only, never raw PII. "
            "Called by hacienda skills after each anonymize/rehydrate round-trip."
        )
    )
    async def session_audit_append(
        session_id: str, event: str, payload: dict
    ) -> dict:
        _audit_for(session_id).append(event, payload)
        return {"ok": True}

    @mcp.tool(
        description=(
            "Read the current Cowork session's redaction audit log. "
            "Returns a list of {timestamp, event, payload} records in write order."
        )
    )
    async def session_audit_read(session_id: str) -> list[dict]:
        return _audit_for(session_id).read()

    from piighost.mcp.bootstrap import ensure_data_dir, ensure_vault_key

    @mcp.tool(
        description=(
            "Idempotent first-run setup for a Cowork client folder. "
            "Ensures the hacienda data directory and vault key exist, creates "
            "the project if missing. Safe to call on every session start."
        )
    )
    async def bootstrap_client_folder(folder: str) -> dict:
        from piighost.mcp.folder import project_name_for_folder
        data_dir = Path(
            os.environ.get("HACIENDA_DATA_DIR", Path.home() / ".hacienda")
        )
        ensure_data_dir(data_dir)
        key = ensure_vault_key(data_dir=data_dir)
        project = project_name_for_folder(Path(folder))

        existing = {p.name for p in await svc.list_projects()}
        if project not in existing:
            # Description contains only the project hash — never the folder
            # path, which would surface via list_projects and leak client names
            # (PII) to the model. See CLAUDE.md "Never return raw PII".
            await svc.create_project(project, description=f"hacienda project {project}")

        return {
            "folder": folder,
            "project": project,
            "data_dir": str(data_dir),
            "vault_key_provisioned": bool(key),
        }

    @mcp.resource("piighost://vault/stats")
    async def vault_stats_resource() -> str:
        stats = svc._vault.stats()
        return f"Total entities: {stats.total}\nBy label: {stats.by_label}"

    @mcp.resource("piighost://vault/recent")
    async def vault_recent_resource() -> str:
        entries = svc._vault.list_entities(limit=10)
        lines = [f"{e.token} [{e.label}] seen {e.occurrence_count}x" for e in entries]
        return "\n".join(lines) if lines else "(empty vault)"

    @mcp.resource("piighost://index/status")
    async def index_status_resource() -> str:
        import json
        status = await svc.index_status()
        state = "ready" if status.files else "empty"
        payload = {
            "state": state,
            "total_docs": status.total_docs,
            "total_chunks": status.total_chunks,
            "last_update": _last_update_iso(status.files),
            "errors": [],
        }
        return json.dumps(payload)

    @mcp.resource("piighost://folders/{b64_path}/status")
    async def folder_status_resource(b64_path: str) -> str:
        import base64
        import json
        # Decode folder path. Add padding back if it was stripped.
        padding = "=" * (-len(b64_path) % 4)
        try:
            folder = base64.urlsafe_b64decode(b64_path + padding).decode("utf-8")
        except Exception:
            return json.dumps({"error": "invalid base64url folder path"})
        project = project_name_for_folder(Path(folder))
        try:
            status = await svc.index_status(project=project)
        except Exception:  # project may not exist yet
            return json.dumps({
                "folder": folder,
                "project": project,
                "state": "empty",
                "progress": {"done": 0, "total": 0},
                "last_update": None,
                "errors": ["index_status unavailable"],
            })
        payload = {
            "folder": folder,
            "project": project,
            "state": "ready" if status.total_docs else "empty",
            "progress": {"done": status.total_docs, "total": status.total_docs},  # v0: no partial-progress tracking
            "last_update": _last_update_iso(status.files),
            "errors": [],
        }
        return json.dumps(payload)

    @mcp.resource("piighost://projects")
    async def projects_resource() -> str:
        import json
        projects = await svc.list_projects()
        payload = [
            {
                "name": p.name,
                "description": p.description,
                "created_at": p.created_at,
                "last_accessed_at": p.last_accessed_at,
            }
            for p in projects
        ]
        return json.dumps(payload, indent=2)

    @mcp.resource("piighost://projects/{name}/stats")
    async def project_stats_resource(name: str) -> str:
        stats = await svc.vault_stats(project=name)
        status = await svc.index_status(project=name)
        return (
            f"Project: {name}\n"
            f"Vault entities: {stats.total}\n"
            f"Indexed docs: {status.total_docs}\n"
            f"Total chunks: {status.total_chunks}\n"
        )

    return mcp, svc


def run_mcp(vault_dir: Path, *, transport: str = "stdio") -> None:
    async def _start() -> None:
        mcp, svc = await build_mcp(vault_dir)
        try:
            await mcp.run_async(transport=transport)
        finally:
            await svc.close()

    asyncio.run(_start())
