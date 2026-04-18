from __future__ import annotations

from .._util import logger
from ..constants import SETTINGS_FILENAME
from ..third_party.semantic_version import NpmSpec  # pyright: ignore[reportPrivateLocalImportUsage]
from .node_runner import ElectronRunnerLocal
from .node_runner import NodeRunner
from .node_runner import NodeRunnerCustom
from .node_runner import NodeRunnerLocal
from .node_runner import NodeRunnerPath
from LSP.plugin import ST_STORAGE_PATH
from pathlib import Path
from sublime_lib import ResourcePath
from typing import cast
from typing import TYPE_CHECKING
import sublime

if TYPE_CHECKING:
    from LSP.plugin import OnPreStartContext


NO_NODE_FOUND_MESSAGE = 'Could not start {package_name} due to not being able to resolve suitable Node.js \
runtime on the PATH. Press the "Download Node.js" button to get required Node.js version \
(note that it will be used only by LSP and will not affect your system otherwise).'


class NodeManager:
    @classmethod
    def on_pre_start_async(
        cls,
        context: OnPreStartContext,
        node_version_requirement: str,
        plugin_storage_path: Path,
        server_directory: Path,
        server_binary_path: Path,
    ) -> None:
        package_name = plugin_storage_path.name
        node_runner = NodeManager.resolve(package_name, node_version_requirement)
        destination_server_directory = plugin_storage_path / server_directory
        source_server_path = ResourcePath('Packages', package_name, server_directory)
        node_runner.install_project_dependencies(plugin_storage_path / server_directory, source_server_path)
        context.configuration.env.update(node_runner.node_env())
        context.variables.update({
            'node_bin': str(node_runner.node_binary_path()),
            'server_path': str(destination_server_directory / server_binary_path),
        })

    @classmethod
    def resolve(cls, package_name: str, required_node_version: str) -> NodeRunner:
        node_runtime = cls._resolve_node_runtime(package_name, NpmSpec(required_node_version))
        print(f'Resolved Node.js Runtime for package {package_name}: {node_runtime}')
        return node_runtime

    @classmethod
    def _resolve_node_runtime(cls, package_name: str, required_node_version: NpmSpec) -> NodeRunner:
        resolved_runtime: NodeRunner | None = None
        default_runtimes = ['system', 'local', 'custom']
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
            elif runtime_type == 'custom':
                custom_node_path = settings.get('nodejs_runtime_node_directory_path')
                log_lines.append(
                    f'Resolving Node.js Runtime for custom path {custom_node_path} for package {package_name}...')
                custom_runtime = NodeRunnerCustom(Path(custom_node_path))
                try:
                    custom_runtime.check_binary_present()
                except Exception as ex:
                    log_lines.append(f' * Failed: {ex}')
                    continue
                try:
                    custom_runtime.check_satisfies_version(required_node_version)
                    resolved_runtime = custom_runtime
                    break
                except Exception as ex:
                    log_lines.append(f' * {ex}')
            elif runtime_type == 'local':
                log_lines.append(f'Resolving Node.js Runtime from lsp_utils for package {package_name}...')
                use_electron = cast('bool', settings.get('local_use_electron') or False)
                runtime_dir = Path(ST_STORAGE_PATH) / 'lsp_utils' / 'node-runtime'
                local_runner = ElectronRunnerLocal(runtime_dir) if use_electron else NodeRunnerLocal(runtime_dir)
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
