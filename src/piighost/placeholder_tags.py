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
a :class:`~piighost.placeholder.RedactPlaceholderFactory`-based
pipeline to the middleware) becomes a static error instead of a
runtime surprise.

The taxonomy is **hierarchical** so the type-checker can apply
Liskov substitution: every ``PreservesIdentity`` token also preserves
the label, every ``PreservesIdentityOpaque`` token also preserves the
identity, and so on.  A consumer asking for a weaker tag accepts any
stronger one via covariance on
:class:`~piighost.placeholder.AnyPlaceholderFactory`.

Hierarchy, from weakest to strongest::

    PlaceholderPreservation
    └── PreservesNothing                 -- ``[REDACT]`` (constant)
        └── PreservesLabel               -- ``<PERSON>``
            ├── PreservesShape           -- ``j***@mail.com``
            └── PreservesIdentity        -- unique reversible id
                ├── PreservesIdentityOpaque       -- ``<<PERSON_1>>``
                └── PreservesIdentityRealistic    -- looks like real data
                    ├── PreservesIdentityHashed   -- ``a1b2c3d4@anon.local``
                    └── PreservesIdentityFaker    -- ``john.doe@example.com``

A factory picks the **most specific** tag that matches its guarantees.
``CounterPlaceholderFactory`` and ``HashPlaceholderFactory`` declare
``PreservesIdentityOpaque``; ``FakerPlaceholderFactory`` declares
``PreservesIdentityFaker``.  A consumer typed against
``PreservesIdentity`` accepts all four sub-tags via covariance, while
a consumer typed against ``PreservesIdentityOpaque`` rejects the
realistic ones at type-check time.
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


class PreservesShape(PreservesLabel):
    """The placeholder preserves part of the original value.

    The masked form (``p***@mail.com``) implicitly carries the label
    via the format, but two distinct entities with similar shapes can
    collide on the same token, and the masked token can also collide
    with a real value in a tool response.  Unsafe for deanonymisation
    that relies on token uniqueness.
    """


class PreservesIdentity(PreservesLabel):
    """The placeholder uniquely identifies each entity.

    Two distinct entities always get distinct tokens, and the same
    entity seen twice gets the same token.  This is the only level
    safe with :class:`~piighost.middleware.ToolCallStrategy.FULL` and
    :class:`~piighost.middleware.ToolCallStrategy.INBOUND_ONLY`.

    Sub-tags refine the *realism* axis: opaque tokens are clearly not
    real data, while realistic tokens look like the original format.
    """


class PreservesIdentityOpaque(PreservesIdentity):
    """The placeholder is unique and clearly synthetic.

    Tokens like ``<<PERSON_1>>`` or ``<PERSON:a1b2c3d4>`` cannot be
    confused with real data, are easy to scan in logs, and never
    coincidentally collide with a real value.
    """


class PreservesIdentityRealistic(PreservesIdentity):
    """The placeholder is unique but looks like real data.

    Realistic tokens pass downstream format validation (email regex,
    name patterns, etc.) at the cost of looking indistinguishable
    from genuine values.  Refined by :class:`PreservesIdentityHashed`
    (collision-proof) and :class:`PreservesIdentityFaker` (collision
    possible with real-world values).
    """


class PreservesIdentityHashed(PreservesIdentityRealistic):
    """Realistic-format placeholder whose content is a hash.

    The token mimics the original format (e.g.
    ``a1b2c3d4@anonymized.local``) but its content is derived from a
    hash, so it is **unique and impossible to coincidentally match**
    a real-world value.
    """


class PreservesIdentityFaker(PreservesIdentityRealistic):
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
    "PreservesIdentityFaker",
    "PreservesIdentityHashed",
    "PreservesIdentityOpaque",
    "PreservesIdentityRealistic",
    "PreservesLabel",
    "PreservesNothing",
    "PreservesShape",
    "get_preservation_tag",
]
