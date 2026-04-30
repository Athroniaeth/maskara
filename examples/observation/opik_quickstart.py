# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "piighost[cache,opik] @ file://${PROJECT_ROOT}",
#     "python-dotenv>=1.0",
# ]
# ///
"""Demo: anonymize text with piighost while logging to Opik.

Runs three anonymisations to demonstrate thread_id and metadata
propagation. Two threads (``user-A`` with two consecutive turns and
``user-B`` with one) so the resulting traces let you eyeball:

* parent trace ``piighost.anonymize_pipeline`` with input/output
* four child spans: detect, link, placeholder, guard
* ``thread_id`` grouping (user-A stays separate from user-B; piighost
  forwards the pipeline's session id onto Opik's ``thread_id`` field
  which is Opik's name for the conversation-grouping channel)
* arbitrary metadata attached at trace creation

Set ``OPIK_API_KEY`` (and optionally ``OPIK_WORKSPACE`` /
``OPIK_PROJECT_NAME``) in a ``.env`` at the repo root, then run::

    uv run examples/observation/opik_quickstart.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv
from opik import Opik

from piighost import Anonymizer, ExactMatchDetector, LabelCounterPlaceholderFactory
from piighost.observation.opik import OpikObservationService
from piighost.pipeline.thread import ThreadAnonymizationPipeline

load_dotenv()


def _check_env() -> None:
    if not os.getenv("OPIK_API_KEY"):
        sys.exit(
            "Missing env var OPIK_API_KEY. "
            "Set it with the key from your Opik account "
            "(Settings → API Keys), and optionally OPIK_WORKSPACE "
            "/ OPIK_PROJECT_NAME."
        )


async def main() -> None:
    _check_env()

    opik_client = Opik(
        api_key=os.environ["OPIK_API_KEY"],
        workspace=os.getenv("OPIK_WORKSPACE"),
        project_name=os.getenv("OPIK_PROJECT_NAME", "piighost-quickstart"),
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
    # Nothing reaches Opik, the pipeline runs at its raw speed. This is
    # what every existing piighost user gets out of the box without
    # changing anything.
    silent_pipeline = ThreadAnonymizationPipeline(
        detector=detector,
        anonymizer=anonymizer,
        # observation= omitted → NoOpObservationService used internally
    )

    silent, _ = await silent_pipeline.anonymize(
        "Patrick lives in Paris.",
        thread_id="silent-A",
    )
    print(f"[no-op default] anonymized: {silent!r} (no Opik trace)")

    # ----- Demo 2: OpikObservationService → traces in Opik --------------
    # Opik will log each anonymisation under the configured project.
    observation = OpikObservationService(opik_client)

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

    opik_client.flush()
    print(
        "\nDone. Open the Opik UI: 'piighost.anonymize_pipeline' traces "
        "filtered by thread id 'user-A' or 'user-B' show the 4-stage tree."
    )


if __name__ == "__main__":
    asyncio.run(main())
