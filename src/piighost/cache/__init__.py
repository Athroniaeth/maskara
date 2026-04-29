"""Optional aiocache backends shipped with PIIGhost.

The default cache (``SimpleMemoryCache`` from aiocache) is process-local
and fine for single-instance deployments.  This subpackage hosts
backends that survive a restart or are shareable across workers.

Each backend is gated behind an optional extra; importing the module
without the corresponding dependency raises ``ImportError`` with a
direct install hint.
"""
