"""
G'lam OS App SDK & G'lamor Controller Core Package.
Provides PC-side ELF ABI preflight checking, .gla (compat .spk) packaging,
multi-file Xtensa project building, and 3-channel device deployment.
"""

BRAND_NAME = "G'lam"
OS_NAME = "G'lam OS"
CONTROLLER_NAME = "G'lamor"
STUDIO_NAME = "G'lamor"
STUDIO_VERSION = "1.0.0"

PKG_EXT = ".gla"
LEGACY_PKG_EXT = ".spk"
GLA_MAGIC = b"GLAM"
LEGACY_SPK_MAGIC = b"SWPK"
PKG_VERSION = 1
ABI_VERSION = 1

__all__ = [
    "BRAND_NAME",
    "OS_NAME",
    "CONTROLLER_NAME",
    "STUDIO_NAME",
    "STUDIO_VERSION",
    "PKG_EXT",
    "LEGACY_PKG_EXT",
    "GLA_MAGIC",
    "LEGACY_SPK_MAGIC",
    "PKG_VERSION",
    "ABI_VERSION",
]
