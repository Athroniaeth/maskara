import importlib.util

if importlib.util.find_spec("faker") is not None:
    from piighost.ph_factory.faker import FakerPlaceholderFactory

    __all__ = ["FakerPlaceholderFactory"]
else:
    __all__ = []
