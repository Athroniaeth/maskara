# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "piighost[cache,langfuse] @ file://${PROJECT_ROOT}",
#     "python-dotenv>=1.0",
# ]
# ///
"""Demo: anonymize text with piighost while logging to Langfuse.

Runs three anonymisations to demonstrate session_id and metadata
propagation. Two threads (``user-A`` with two consecutive turns and
``user-B`` with one) so the resulting traces let you eyeball:

* parent observation ``piighost.anonymize_pipeline`` with input/output
* four child observations: detect, link, placeholder, guard
* ``session.id`` grouping (user-A stays separate from user-B)
* arbitrary metadata propagated via ``update_trace``

Set ``LANGFUSE_PUBLIC_KEY`` / ``LANGFUSE_SECRET_KEY`` / ``LANGFUSE_HOST``
in a ``.env`` at the repo root, then run::

    uv run examples/observation/langfuse_quickstart.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv
from langfuse import Langfuse

from piighost import Anonymizer, ExactMatchDetector, LabelCounterPlaceholderFactory
from piighost.observation.langfuse import LangfuseObservationService
from piighost.pipeline.thread import ThreadAnonymizationPipeline

load_dotenv()


def _check_env() -> None:
    missing = [
        v for v in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY") if not os.getenv(v)
    ]
    if missing:
        sys.exit(
            "Missing env vars: " + ", ".join(missing) + ". "
            "Set them with the keys from your Langfuse project (Settings → API Keys)."
        )


async def main() -> None:
    _check_env()

    langfuse = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
    )

    detector = ExactMatchDetector(
        [
            ("Patrick", "PERSON"),
            ("Marie", "PERSON"),
            ("Paris", "LOCATION"),
            ("Lyon", "LOCATION"),
        ],
    )
    ph_factory = LabelCounterPlaceholderFactory()
    anonymizer = Anonymizer(ph_factory=ph_factory)

    # ----- Demo 1: no observation argument → NoOp default ---------------
    # Nothing reaches Langfuse, no per-stage sleep, the pipeline runs at
    # its raw speed. This is what every existing piighost user gets out
    # of the box without changing anything.
    silent_pipeline = ThreadAnonymizationPipeline(
        detector=detector,
        anonymizer=anonymizer,
        # observation= omitted → NoOpObservationService used internally
    )

    silent, _ = await silent_pipeline.anonymize(
        "Patrick lives in Paris.",
        thread_id="silent-A",
    )
    print(f"[no-op default] anonymized: {silent!r} (no Langfuse trace)")

    # ----- Demo 2: LangfuseObservationService → traces in Langfuse ------
    # Langfuse will log each anonymisation
    observation = LangfuseObservationService(langfuse)

    pipeline = ThreadAnonymizationPipeline(
        detector=detector,
        anonymizer=anonymizer,
        observation=observation,
    )

    a1, _ = await pipeline.anonymize(
        "Patrick lives in Paris.",
        thread_id="user-A",
        metadata={"tenant": "acme", "doc_kind": "contract"},
    )
    print(f"[user-A] turn 1: {a1!r}")

    a2, _ = await pipeline.anonymize(
        "Patrick wrote to Marie about Paris.",
        thread_id="user-A",
        metadata={"tenant": "acme", "doc_kind": "email"},
    )
    print(f"[user-A] turn 2: {a2!r}")

    b1, _ = await pipeline.anonymize(
        "Marie lives in Lyon.",
        thread_id="user-B",
        metadata={"tenant": "acme-eu", "doc_kind": "contract"},
    )
    print(f"[user-B] turn 1: {b1!r}")

    langfuse.flush()
    print(
        "\nDone. Open the Langfuse UI: 'piighost.anonymize_pipeline' traces "
        "filtered by session id 'user-A' or 'user-B' show the 4-stage tree."
    )


if __name__ == "__main__":
    asyncio.run(main())
