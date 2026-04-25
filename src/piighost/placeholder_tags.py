"""Marker types describing how much information a placeholder preserves.

Placeholder factories differ in what they keep of an entity after
replacement.  Some produce a distinct, reversible token per entity;
others collapse every entity of the same label into the same string;
others leak part of the original value.  The consumers of a factory
(anonymizer, pipeline, middleware) often care about this level of
preservation: for instance, ``PIIAnonymizationMiddleware`` in anything
other than :class:`~piighost.middleware.ToolCallStrategy.PASSTHROUGH`
mode requires placeholders that uniquely identify each entity so
arguments can be deanonymised reliably.

The tags declared here are **phantom** types: they exist only for the
type checker.  They attach a "preservation level" to a factory class
via a generic parameter, so an incompatible combination (e.g. passing
a :class:`~piighost.placeholder.LabelPlaceholderFactory`-based
pipeline to the middleware) becomes a static error instead of a
runtime surprise.

Two **independent axes** organise the taxonomy:

* **Label** — does the placeholder reveal the entity type?
  ``<PERSON>`` reveals it; ``[REDACT]`` does not.
* **Identity** — does the placeholder uniquely identify the entity?
  ``<<PERSON:1>>`` is unique per entity; ``<PERSON>`` collapses every
  person.

The four base combinations correspond to four base tags:

* :class:`PreservesNothing`           — neither axis (e.g. ``[REDACT]``)
* :class:`PreservesLabel`             — label only (e.g. ``<PERSON>``)
* :class:`PreservesIdentity`          — identity only (e.g. ``[a1b2c3d4]``)
* :class:`PreservesLabeledIdentity`   — both (e.g. ``<<PERSON:1>>``)

``PreservesLabeledIdentity`` multi-inherits from both
``PreservesLabel`` and ``PreservesIdentity``; via covariance on
:class:`~piighost.placeholder.AnyPlaceholderFactory`, a consumer typed
against ``PreservesLabel`` accepts a labeled-identity factory, and a
consumer typed against ``PreservesIdentity`` accepts both
identity-only and labeled-identity factories.  This is the
"A is a B but not every B is an A" relation the user sees as the
hierarchy: every ``PreservesLabeledIdentity`` is a
``PreservesLabel`` and a ``PreservesIdentity``, but not the reverse.

A *realism* sub-axis refines ``PreservesLabeledIdentity``:

* :class:`PreservesLabeledIdentityOpaque`     — clearly synthetic token
  (``<<PERSON:1>>``, ``<PERSON:a1b2c3d4>``).
* :class:`PreservesLabeledIdentityRealistic`  — looks like real data.
* :class:`PreservesLabeledIdentityHashed`     — realistic format with
  hashed content (``a1b2c3d4@anonymized.local``).
* :class:`PreservesLabeledIdentityFaker`      — Faker output, may
  collide with real-world values (``john.doe@example.com``).

:class:`PreservesShape` is a special label-extending case: the token
keeps a partial fragment of the original (``j***@mail.com``).  It
implies the label via its format but does *not* guarantee uniqueness,
so it is a sibling of identity in the hierarchy.

The full inheritance graph::

    PlaceholderPreservation
    └── PreservesNothing
        ├── PreservesLabel
        │   └── PreservesShape
        ├── PreservesIdentity
        │   └── PreservesIdentityOnly
        └── PreservesLabeledIdentity (PreservesLabel, PreservesIdentity)
            ├── PreservesLabeledIdentityOpaque
            └── PreservesLabeledIdentityRealistic
                ├── PreservesLabeledIdentityHashed
                └── PreservesLabeledIdentityFaker
"""


class PlaceholderPreservation:
    """Root marker for placeholder preservation tags.

    Subclasses are used as phantom type parameters on
    :class:`~piighost.placeholder.AnyPlaceholderFactory` and on the
    anonymizer/pipeline types that carry a factory.
    """


class PreservesNothing(PlaceholderPreservation):
    """The placeholder is a constant marker carrying no information.

    Every entity collapses to the same token (e.g. ``[REDACT]``).
    Deanonymisation is not possible; only use with
    :class:`~piighost.middleware.ToolCallStrategy.PASSTHROUGH` or
    outside the middleware entirely.
    """


class PreservesLabel(PreservesNothing):
    """The placeholder preserves the entity label.

    Different entities sharing a label collide into the same token
    (``<PERSON>``).  Suitable for one-shot redaction but cannot be
    reversed, which rules it out for the middleware's tool-call
    handling outside of
    :class:`~piighost.middleware.ToolCallStrategy.PASSTHROUGH`.
    """


class PreservesIdentity(PreservesNothing):
    """The placeholder uniquely identifies each entity.

    Two distinct entities always get distinct tokens, and the same
    entity seen twice gets the same token.  This is the abstract
    base for any identity-preserving tag, regardless of whether the
    label is also revealed.

    The middleware narrows on this base: every concrete sub-tag
    (``PreservesIdentityOnly``, ``PreservesLabeledIdentity*``) is
    accepted via covariance.
    """


class PreservesIdentityOnly(PreservesIdentity):
    """Unique reversible id without revealing the entity type.

    Tokens like ``[a1b2c3d4]`` or ``<a1b2c3d4>`` carry a per-entity
    hash but no label, so the LLM can tell two entities apart while
    learning nothing about whether they are persons, emails, or
    credit cards.  No built-in factory ships this scheme; it is the
    recommended tag for a user factory that hashes without a label
    prefix.
    """


class PreservesShape(PreservesLabel):
    """The placeholder preserves part of the original value.

    The masked form (``p***@mail.com``) implicitly carries the label
    via the format, but two distinct entities with similar shapes can
    collide on the same token, and the masked token can also collide
    with a real value in a tool response.  Unsafe for deanonymisation
    that relies on token uniqueness.
    """


class PreservesLabeledIdentity(PreservesLabel, PreservesIdentity):
    """The placeholder reveals both the label and a unique identity.

    Multi-inherits :class:`PreservesLabel` and :class:`PreservesIdentity`
    so a consumer typed against either base accepts a labeled-identity
    factory.  Refined further on the *realism* axis by
    :class:`PreservesLabeledIdentityOpaque` and
    :class:`PreservesLabeledIdentityRealistic`.
    """


class PreservesLabeledIdentityOpaque(PreservesLabeledIdentity):
    """Labeled, unique, and clearly synthetic.

    Tokens like ``<<PERSON:1>>`` or ``<PERSON:a1b2c3d4>`` cannot be
    confused with real data, are easy to scan in logs, and never
    coincidentally collide with a real value.
    """


class PreservesLabeledIdentityRealistic(PreservesLabeledIdentity):
    """Labeled, unique, and visually plausible.

    Realistic tokens pass downstream format validation (email regex,
    name patterns, etc.) at the cost of looking indistinguishable
    from genuine values.  Refined by
    :class:`PreservesLabeledIdentityHashed` (collision-proof) and
    :class:`PreservesLabeledIdentityFaker` (collision possible with
    real-world values).
    """


class PreservesLabeledIdentityHashed(PreservesLabeledIdentityRealistic):
    """Realistic-format placeholder whose content is a hash.

    The token mimics the original format (e.g.
    ``a1b2c3d4@anonymized.local``) but its content is derived from a
    hash, so it is **unique and impossible to coincidentally match**
    a real-world value.
    """


class PreservesLabeledIdentityFaker(PreservesLabeledIdentityRealistic):
    """Plausible-realistic placeholder produced by Faker.

    Tokens like ``john.doe@example.com`` or ``Jean Dupont`` are
    indistinguishable from genuine data.  Each entity still maps to a
    unique token, but a Faker value can coincidentally land on a real
    person's actual data, which the middleware cannot detect during
    string replacement.
    """


def get_preservation_tag(factory: object) -> type[PlaceholderPreservation] | None:
    """Return the preservation tag a factory class advertises, if any.

    Walks the MRO of ``type(factory)`` looking for a generic base
    ``AnyPlaceholderFactory[<tag>]`` and returns the tag class. Returns
    ``None`` when no tag can be recovered (untyped factory, or a
    factory that does not subclass the generic protocol).

    This utility powers the runtime check performed by
    :class:`~piighost.pipeline.thread.ThreadAnonymizationPipeline`: it
    mirrors the static-typing constraint without duplicating the list
    of rejected factory classes.
    """
    from typing import get_args, get_origin

    # Imported lazily to avoid a cycle with ``piighost.placeholder``.
    from piighost.placeholder import AnyPlaceholderFactory

    for base in type(factory).__mro__:
        for orig in getattr(base, "__orig_bases__", ()):
            if get_origin(orig) is not AnyPlaceholderFactory:
                continue
            args = get_args(orig)
            if (
                args
                and isinstance(args[0], type)
                and issubclass(args[0], PlaceholderPreservation)
            ):
                return args[0]
    return None


__all__ = [
    "PlaceholderPreservation",
    "PreservesIdentity",
    "PreservesIdentityOnly",
    "PreservesLabel",
    "PreservesLabeledIdentity",
    "PreservesLabeledIdentityFaker",
    "PreservesLabeledIdentityHashed",
    "PreservesLabeledIdentityOpaque",
    "PreservesLabeledIdentityRealistic",
    "PreservesNothing",
    "PreservesShape",
    "get_preservation_tag",
]
