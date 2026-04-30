"""SQLAlchemy-backed aiocache backend.

Stores cache entries in a single table on any database that has an
async SQLAlchemy driver.  Tested targets:

* SQLite via ``aiosqlite`` for development and single-host production.
* PostgreSQL via ``asyncpg`` for multi-worker production deployments.

The backend mirrors the ``aiocache.BaseCache`` API used by
``AnonymizationPipeline`` so that existing pipelines accept it as a
drop-in replacement for ``SimpleMemoryCache`` / ``RedisCache``.

Example:
    >>> import asyncio
    >>> from piighost.cache.sqlalchemy import SQLAlchemyCache
    >>> async def demo():
    ...     cache = SQLAlchemyCache(url="sqlite+aiosqlite:///:memory:")
    ...     await cache.create_schema()
    ...     await cache.set("k", {"v": 1})
    ...     return await cache.get("k")
    >>> asyncio.run(demo())
    {'v': 1}
"""

from __future__ import annotations

import importlib.util
import time
from typing import Any, Iterable, cast

if importlib.util.find_spec("sqlalchemy") is None:
    raise ImportError(
        "You must install SQLAlchemy to use SQLAlchemyCache, "
        "please install piighost[sqlalchemy]"
    )

from aiocache.base import BaseCache
from aiocache.serializers import PickleSerializer
from sqlalchemy import (
    Column,
    Float,
    LargeBinary,
    MetaData,
    String,
    Table,
    delete,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)


_DEFAULT_TABLE_NAME = "piighost_cache"
_metadata_cache: dict[str, MetaData] = {}


def _build_table(table_name: str) -> Table:
    """Return (and cache) the cache ``Table`` for *table_name*.

    Reusing the same ``MetaData``/``Table`` object across instances that
    share a name keeps SQLAlchemy from raising
    ``InvalidRequestError: Table is already defined``.
    """
    if table_name in _metadata_cache:
        meta = _metadata_cache[table_name]
        return meta.tables[table_name]
    meta = MetaData()
    table = Table(
        table_name,
        meta,
        Column("key", String(512), primary_key=True),
        Column("value", LargeBinary, nullable=False),
        # Stored as a unix timestamp in seconds (float) so SQLite,
        # PostgreSQL and others all agree on the comparison semantics.
        # NULL means "never expire".
        Column("expires_at", Float, nullable=True),
    )
    _metadata_cache[table_name] = meta
    return table


class SQLAlchemyCache(BaseCache):
    """aiocache backend that persists entries via SQLAlchemy async.

    Args:
        url: SQLAlchemy async URL such as
            ``"sqlite+aiosqlite:///cache.db"`` or
            ``"postgresql+asyncpg://user:pwd@host/db"``.  Mutually
            exclusive with ``engine``.
        engine: An existing ``AsyncEngine`` to reuse.  Useful when the
            application already manages a SQLAlchemy engine and wants
            the cache to share the connection pool.
        table_name: Name of the cache table.  Defaults to
            ``"piighost_cache"``.  Pick a different name to share one
            database between several PIIGhost deployments.
        serializer: aiocache serializer.  Defaults to ``PickleSerializer``
            because the pipeline stores nested Python dicts that contain
            tuples and dataclasses.  Pass ``JsonSerializer()`` if you
            prefer JSON storage and your data is JSON-compatible.
        **kwargs: Forwarded to ``aiocache.BaseCache.__init__`` (namespace,
            timeout, plugins…).
    """

    NAME = "sqlalchemy"

    _engine: AsyncEngine
    _owns_engine: bool
    _session_factory: async_sessionmaker
    _table: Table

    def __init__(
        self,
        url: str | None = None,
        engine: AsyncEngine | None = None,
        table_name: str = _DEFAULT_TABLE_NAME,
        serializer: object | None = None,
        **kwargs: Any,
    ) -> None:
        if (url is None) == (engine is None):
            raise ValueError("Provide exactly one of `url` or `engine`.")

        super().__init__(serializer=serializer or PickleSerializer(), **kwargs)

        if engine is not None:
            self._engine = engine
            self._owns_engine = False
        else:
            # ``url`` is non-None here, narrowed by the
            # ``(url is None) == (engine is None)`` validation above.
            self._engine = create_async_engine(cast(str, url), future=True)
            self._owns_engine = True

        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._table = _build_table(table_name)

    # ------------------------------------------------------------------
    # Schema & lifecycle
    # ------------------------------------------------------------------

    async def create_schema(self) -> None:
        """Create the cache table if it does not exist.

        Idempotent.  Called once at application startup; subsequent
        calls are no-ops.  Skip it if you manage migrations externally
        (Alembic) — the column layout is documented in the module
        docstring.
        """
        async with self._engine.begin() as conn:
            await conn.run_sync(self._table.metadata.create_all)

    async def close(self) -> None:
        """Dispose the underlying engine if this instance owns it.

        No-op when an external engine was provided via ``engine=`` so
        the caller stays in charge of its connection pool.
        """
        if self._owns_engine:
            await self._engine.dispose()

    # ------------------------------------------------------------------
    # aiocache backend protocol
    # ------------------------------------------------------------------
    # Pyrefly flags these as inconsistent overrides because BaseCache
    # declares the _* methods without defaults; aiocache's own backends
    # (SimpleMemoryBackend, RedisBackend) take the same liberty.  We
    # silence the noise rather than adopt a different style from the
    # rest of the aiocache ecosystem.

    async def _get(self, key, encoding="utf-8", _conn=None):  # type: ignore[bad-override]
        async with self._session_factory() as session:
            row = await session.execute(
                select(self._table.c.value, self._table.c.expires_at).where(
                    self._table.c.key == key
                ),
            )
            res = row.one_or_none()
            if res is None:
                return None
            value, expires_at = res
            if expires_at is not None and expires_at <= time.time():
                # Lazy purge: drop the row when read after expiry so
                # the table does not grow unbounded.
                await session.execute(
                    delete(self._table).where(self._table.c.key == key),
                )
                await session.commit()
                return None
            return value

    async def _gets(  # type: ignore[bad-override]
        self,
        key,
        encoding="utf-8",
        _conn=None,
    ):
        return await self._get(key, encoding=encoding, _conn=_conn)

    async def _multi_get(  # type: ignore[bad-override]
        self,
        keys,
        encoding="utf-8",
        _conn=None,
    ):
        if not keys:
            return []
        async with self._session_factory() as session:
            rows = await session.execute(
                select(
                    self._table.c.key,
                    self._table.c.value,
                    self._table.c.expires_at,
                ).where(self._table.c.key.in_(keys)),
            )
            now = time.time()
            by_key: dict[str, object] = {}
            expired: list[str] = []
            for k, v, exp in rows.all():
                if exp is not None and exp <= now:
                    expired.append(k)
                else:
                    by_key[k] = v
            if expired:
                await session.execute(
                    delete(self._table).where(self._table.c.key.in_(expired)),
                )
                await session.commit()
            return [by_key.get(k) for k in keys]

    async def _set(  # type: ignore[bad-override]
        self,
        key,
        value,
        ttl=None,
        _cas_token=None,
        _conn=None,
    ):
        expires_at = (time.time() + ttl) if ttl else None
        async with self._session_factory() as session:
            if _cas_token is not None:
                current = await session.execute(
                    select(self._table.c.value).where(self._table.c.key == key),
                )
                existing = current.scalar_one_or_none()
                if existing != _cas_token:
                    return 0
            await self._upsert(session, [(key, value, expires_at)])
            await session.commit()
            return True

    async def _multi_set(  # type: ignore[bad-override]
        self,
        pairs,
        ttl=None,
        _conn=None,
    ):
        if not pairs:
            return True
        expires_at = (time.time() + ttl) if ttl else None
        rows = [(k, v, expires_at) for k, v in pairs]
        async with self._session_factory() as session:
            await self._upsert(session, rows)
            await session.commit()
            return True

    async def _add(  # type: ignore[bad-override]
        self,
        key,
        value,
        ttl=None,
        _conn=None,
    ):
        async with self._session_factory() as session:
            existing = await session.execute(
                select(self._table.c.key).where(self._table.c.key == key),
            )
            if existing.scalar_one_or_none() is not None:
                raise ValueError(
                    f"Key {key} already exists, use .set to update the value"
                )
            expires_at = (time.time() + ttl) if ttl else None
            await self._upsert(session, [(key, value, expires_at)])
            await session.commit()
            return True

    async def _exists(  # type: ignore[bad-override]
        self,
        key,
        _conn=None,
    ):
        return (await self._get(key)) is not None

    async def _increment(self, key, delta, _conn=None):
        # The cache stores raw bytes after serialization.  Increment
        # only makes sense for an integer payload, which the pipeline
        # never writes, so we keep a minimal implementation that round-
        # trips through int() and stores the result as a UTF-8 string.
        async with self._session_factory() as session:
            current = await session.execute(
                select(self._table.c.value).where(self._table.c.key == key),
            )
            existing = current.scalar_one_or_none()
            if existing is None:
                new_value = delta
            else:
                try:
                    new_value = int(existing) + delta
                except (TypeError, ValueError):
                    raise TypeError("Value is not an integer") from None
            encoded = str(new_value).encode("utf-8")
            await self._upsert(session, [(key, encoded, None)])
            await session.commit()
            return new_value

    async def _expire(  # type: ignore[bad-override]
        self,
        key,
        ttl,
        _conn=None,
    ):
        async with self._session_factory() as session:
            existing = await session.execute(
                select(self._table.c.key).where(self._table.c.key == key),
            )
            if existing.scalar_one_or_none() is None:
                return False
            expires_at = (time.time() + ttl) if ttl else None
            await session.execute(
                self._table.update()
                .where(self._table.c.key == key)
                .values(expires_at=expires_at),
            )
            await session.commit()
            return True

    async def _delete(  # type: ignore[bad-override]
        self,
        key,
        _conn=None,
    ):
        async with self._session_factory() as session:
            result = await session.execute(
                delete(self._table).where(self._table.c.key == key),
            )
            await session.commit()
            return result.rowcount or 0

    async def _clear(  # type: ignore[bad-override]
        self,
        namespace=None,
        _conn=None,
    ):
        async with self._session_factory() as session:
            if namespace:
                await session.execute(
                    delete(self._table).where(
                        self._table.c.key.like(f"{namespace}%"),
                    ),
                )
            else:
                await session.execute(delete(self._table))
            await session.commit()
            return True

    async def _raw(self, command, *args, encoding="utf-8", _conn=None, **kwargs):
        # Avoid exposing arbitrary table operations through aiocache's
        # raw escape hatch.  Callers that need direct DB access should
        # use the engine they own (``engine=`` constructor argument)
        # rather than reaching through the cache.
        raise NotImplementedError(
            "SQLAlchemyCache does not support the raw() escape hatch. "
            "Use the SQLAlchemy engine you injected via `engine=` for "
            "ad-hoc queries.",
        )

    async def _redlock_release(  # type: ignore[bad-override]
        self,
        key,
        value,
    ):
        async with self._session_factory() as session:
            current = await session.execute(
                select(self._table.c.value).where(self._table.c.key == key),
            )
            existing = current.scalar_one_or_none()
            if existing != value:
                return 0
            result = await session.execute(
                delete(self._table).where(self._table.c.key == key),
            )
            await session.commit()
            return result.rowcount or 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _upsert(
        self,
        session,
        rows: Iterable[tuple[str, object, float | None]],
    ) -> None:
        """Dialect-aware upsert.

        Both SQLite (3.24+) and PostgreSQL support
        ``INSERT ... ON CONFLICT DO UPDATE``; SQLAlchemy exposes them
        through dialect-specific ``insert`` constructors.  Other
        dialects fall back to a delete-then-insert sequence inside the
        same transaction.
        """
        rows = list(rows)
        if not rows:
            return
        dialect = self._engine.dialect.name
        values = [{"key": k, "value": v, "expires_at": exp} for k, v, exp in rows]
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(self._table).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[self._table.c.key],
                set_={
                    "value": stmt.excluded.value,
                    "expires_at": stmt.excluded.expires_at,
                },
            )
            await session.execute(stmt)
            return
        if dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            stmt = sqlite_insert(self._table).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[self._table.c.key],
                set_={
                    "value": stmt.excluded.value,
                    "expires_at": stmt.excluded.expires_at,
                },
            )
            await session.execute(stmt)
            return
        # Generic fallback: delete the keys we are about to write so the
        # subsequent INSERT cannot violate the primary-key constraint.
        keys = [v["key"] for v in values]
        await session.execute(
            delete(self._table).where(self._table.c.key.in_(keys)),
        )
        await session.execute(self._table.insert(), values)


__all__ = ["SQLAlchemyCache"]
