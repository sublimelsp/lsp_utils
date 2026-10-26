from __future__ import annotations

NODE_RUNTIME_VERSION = '24.15.0'
NODE_DIST_URL = 'https://github.com/sublimelsp/node-pointer-compression-builds/releases/download/v{version}/{filename}'

# Versions previously installed into the `node-runtime` directory by older lsp_utils releases (including Node.js
# versions of the Electron runtime). Removed automatically. When bumping a runtime version, add the old version here.
OBSOLETE_NODE_RUNTIME_VERSIONS = ('16.15.0', '16.17.1', '18.17.1', '18.18.1', '20.18.0', '22.18.0')
