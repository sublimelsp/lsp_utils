from LSP.plugin.core.typing import Optional
import gzip
import os
import shutil
import sublime
import urllib.request
import zipfile


def log_and_show_message(msg, additional_logs: str = None, show_in_status: bool = True) -> None:
    print(msg, "\n", additional_logs) if additional_logs else print(msg)
    if show_in_status:
        sublime.active_window().status_message(msg)


class ServerVscodeMarketplaceResource(object):
    """Global object providing paths to server resources.
    Also handles the installing and updating of the server in cache.

    setup() needs to be called during (or after) plugin_loaded() for paths to be valid.

    For example, for https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance
        - extension_item_name is "ms-python.vscode-pylance"
        - extension_version is like "2020.10.1"
    """

    extension_download_pattern = "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/{vendor}/vsextensions/{name}/{version}/vspackage"

    def __init__(
        self,
        package_name: str,
        extension_item_name: str,
        extension_version: str,
        server_binary_path: str,
    ) -> None:
        self._initialized = False
        self._is_ready = False
        self._package_name = package_name
        self._extension_item_name = extension_item_name
        self._extension_version = extension_version
        self._binary_path = server_binary_path
        self._package_cache_path = ""
        self._activity_indicator = None

        if (
            not self._package_name
            or not self._extension_item_name
            or not self._extension_version
            or not self._binary_path
        ):
            raise Exception("ServerVscodeMarketplaceResource could not initialize due to wrong input")

    @property
    def ready(self) -> bool:
        return self._is_ready

    @property
    def binary_path(self) -> str:
        return os.path.join(self._package_cache_path, self._binary_path)

    @property
    def package_cache_path(self) -> str:
        return self._package_cache_path

    def setup(self) -> None:
        if self._initialized:
            return

        self._initialized = True
        self._package_cache_path = os.path.join(
            sublime.cache_path(),
            self._package_name,
            "{}~{}".format(self._extension_item_name, self._extension_version),
        )

        if not os.path.isfile(self.binary_path):
            self._download_extension()

        if os.path.isfile(self.binary_path):
            self._is_ready = True

    def cleanup(self) -> None:
        if os.path.isdir(self._package_cache_path):
            shutil.rmtree(self._package_cache_path)

    def _download_extension(self) -> None:
        vsix_path = os.path.join(self._package_cache_path, "extension.vsix")
        extension_vendor, extension_name = self._extension_item_name.split(".")

        response = urllib.request.urlopen(
            self.extension_download_pattern.format(
                vendor=extension_vendor,
                name=extension_name,
                version=self._extension_version,
            )
        )

        response_data = response.read()
        if response.info().get("Content-Encoding") == "gzip":
            response_data = gzip.decompress(response_data)

        os.makedirs(os.path.dirname(vsix_path), exist_ok=True)
        with open(vsix_path, "wb") as f:
            f.write(response_data)
        self._decompress_vsix(vsix_path)

    def _on_install_success(self, _: str) -> None:
        self._is_ready = True
        self._stop_indicator()
        log_and_show_message("{}: Server installed. Sublime Text restart might be required.".format(self._package_name))

    def _on_error(self, error: str) -> None:
        self._stop_indicator()
        log_and_show_message("{}: Error:".format(self._package_name), error)

    def _stop_indicator(self) -> None:
        if self._activity_indicator:
            self._activity_indicator.stop()
            self._activity_indicator = None

    def _decompress_vsix(self, file: str, dst_dir: Optional[str] = None) -> None:
        """
        @brief Decompress the .vsix tarball.

        @param file    The .vsix tarball
        @param dst_dir The destination directory
        """

        if not dst_dir:
            dst_dir = os.path.dirname(file)

        with zipfile.ZipFile(file) as f:
            f.extractall(dst_dir)
