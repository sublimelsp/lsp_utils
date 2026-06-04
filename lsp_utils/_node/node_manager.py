from __future__ import annotations

from .._util import logger
from ..constants import SETTINGS_FILENAME
from ..third_party.semantic_version import NpmSpec  # pyright: ignore[reportPrivateLocalImportUsage]
from .node_runner import NodeRunner
from .node_runner import NodeRunnerLocal
from .node_runner import NodeRunnerPath
from .node_runner import ServerInstalledCallback
from LSP.plugin import ST_STORAGE_PATH
from LSP.plugin.core.logging import debug
from pathlib import Path
from typing import cast
from typing import TYPE_CHECKING
import sublime

if TYPE_CHECKING:
    from LSP.plugin import OnPreStartContext
    from sublime_lib import ResourcePath


NO_NODE_FOUND_MESSAGE = 'Could not start {package_name} due to not being able to resolve suitable Node.js \
runtime on the PATH. Press the "Download Node.js" button to get required Node.js version \
(note that it will be used only by LSP and will not affect your system otherwise).'


class NodeManager:
    @classmethod
    def on_pre_start_async(
        cls,
        context: OnPreStartContext,
        plugin_storage_path: Path,
        server_directory_resource_path: ResourcePath,
        server_binary_path: Path,
        *,
        node_version_requirement: str,
        skip_npm_install: bool = False,
        on_server_installed: ServerInstalledCallback | None = None,
    ) -> Path | None:
        """
        Initialize NodeManager for an LspPlugin.

        Automatically adds support for a root `server_path` package setting that defaults to `"auto"`, meaning
        that the package-managed server instance will be used. It can be overridden to use a custom server binary.

        :param context: The plugin context.
        :param plugin_storage_path: The path to the plugin's storage (`cls.plugin_storage_path`).
        :param server_directory_resource_path: The `ResourcePath` to the directory that contains the server's
            `package.json` file. Must have a `Packages/<package_name>/` prefix followed by the path to
            the directory containing `package.json` within the package.
        :param server_binary_path: The path of the file used to start the server, relative to the server's
            directory that contains `package.json`. For example `Path('node_modules', 'server', 'start.js')`.
        :param node_version_requirement: NPM semantic version (typically a range) specifying which Node.js version
            is required by the server. Examples:

            - `16.1.1` - only allows a single version
            - `16.x` - allows any build for major version 16
            - `>=16` - allows version 16 and above
            - `16 - 18` - allows any version between 16 and 18 inclusive (spaces around the dash are required)

            See also: https://semver.npmjs.com/
        :param on_server_installed: Callback called when the server gets installed or updated. Gets passed the Path to
            the server directory (containing 'package.json').

        :returns: Path to the server directory (containing 'package.json') if the server is managed.
        """
        package_name = plugin_storage_path.name
        node_runner = NodeManager.resolve(package_name, node_version_requirement)
        if hasattr(context.configuration, 'root_settings'):
            server_path = context.configuration.root_settings.get('server_path')
        elif hasattr(context.configuration, 'server_path'):
            server_path = context.configuration.server_path
        else:
            server_path = 'auto'
        destination_server_directory = None
        if not server_path or server_path == 'auto':
            destination_server_directory = plugin_storage_path / server_directory_resource_path.name
            node_runner.install_project_dependencies(
                server_directory_resource_path, destination_server_directory, skip_npm_install=skip_npm_install,
                on_server_installed=on_server_installed)
            server_path = str(destination_server_directory / server_binary_path)
        context.configuration.env.update(node_runner.node_env())
        context.variables.update({
            'node_bin': str(node_runner.node_binary_path()),
            'server_path': str(server_path),
        })
        return destination_server_directory

    @classmethod
    def resolve(cls, package_name: str, required_node_version: str) -> NodeRunner:
        node_runtime = cls._resolve_node_runtime(package_name, NpmSpec(required_node_version))
        debug(f'Resolved Node.js Runtime for package {package_name}: {node_runtime}')
        return node_runtime

    @classmethod
    def _resolve_node_runtime(cls, package_name: str, required_node_version: NpmSpec) -> NodeRunner:
        resolved_runtime: NodeRunner | None = None
        default_runtimes = ['system', 'local', 'local-test']
        settings = sublime.load_settings(SETTINGS_FILENAME)
        selected_runtimes = cast('list[str]', settings.get('nodejs_runtime') or default_runtimes)
        log_lines = ['--- lsp_utils Node.js resolving start ---']
        for runtime_type in selected_runtimes:
            if runtime_type == 'system':
                log_lines.append(f'Resolving Node.js Runtime in env PATH for package {package_name}...')
                path_runtime = NodeRunnerPath()
                try:
                    path_runtime.check_binary_present()
                except Exception as ex:
                    log_lines.append(f' * Failed: {ex}')
                    continue
                try:
                    path_runtime.check_satisfies_version(required_node_version)
                    resolved_runtime = path_runtime
                    break
                except Exception as ex:
                    log_lines.append(f' * {ex}')
            elif runtime_type in {'local', 'local-test'}:
                log_lines.append(f'Resolving Node.js Runtime from lsp_utils for package {package_name}...')
                runtime_dir = Path(ST_STORAGE_PATH) / 'lsp_utils' / 'node-runtime'
                local_runner = NodeRunnerLocal(runtime_dir)
                try:
                    local_runner.check_binary_present()
                except Exception as ex:
                    log_lines.append(f' * Binaries check failed: {ex}')
                    if selected_runtimes[0] != 'local' and not sublime.ok_cancel_dialog(
                            NO_NODE_FOUND_MESSAGE.format(package_name=package_name), 'Download Node.js'):
                        log_lines.append(' * Download skipped')
                        continue
                    try:
                        local_runner.install_node()
                    except Exception as ex:
                        log_lines.append(f' * Failed during installation: {ex}')
                        continue
                    try:
                        local_runner.check_binary_present()
                    except Exception as ex:
                        log_lines.append(f' * Failed: {ex}')
                        continue
                try:
                    local_runner.check_satisfies_version(required_node_version)
                    resolved_runtime = local_runner
                    break
                except Exception as ex:
                    log_lines.append(f' * {ex}')
        if not resolved_runtime:
            log_lines.append('--- lsp_utils Node.js resolving end ---')
            logger.debug('\n'.join(log_lines))
            msg = 'Failed resolving Node.js Runtime. Please check in the console for more details.'
            raise Exception(msg)
        return resolved_runtime
