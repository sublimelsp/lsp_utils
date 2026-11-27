from __future__ import annotations

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec
from importlib.util import spec_from_loader
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING
from unittest import TestCase
import tarfile

if TYPE_CHECKING:
    from types import ModuleType


def _load_downloads_module() -> ModuleType:
    # Load the module from its file so that the `lsp_utils` package (and its dependencies like `sublime_lib`)
    # doesn't need to be importable in the test environment.
    path = Path(__file__).parent.parent / 'lsp_utils' / '_util' / 'downloads.py'
    loader = SourceFileLoader('lsp_utils_downloads_under_test', str(path))
    spec = spec_from_loader(loader.name, loader)
    assert spec is not None
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


_downloads = _load_downloads_module()
extract_archive = _downloads.extract_archive
get_top_level_directory = _downloads.get_top_level_directory


def create_tar(archive_path: Path, names: list[str]) -> None:
    """Create a tar.gz archive with given member names. Names ending with `/` become directories."""
    with tarfile.open(str(archive_path), 'w:gz') as archive:
        for name in names:
            info = tarfile.TarInfo(name)
            if name.endswith('/'):
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                archive.addfile(info)
            else:
                data = b'content'
                info.size = len(data)
                info.mode = 0o644
                archive.addfile(info, BytesIO(data))


class GetTopLevelDirectoryTests(TestCase):
    def test_plain_names(self) -> None:
        names = ['server-1.0/', 'server-1.0/bin/', 'server-1.0/bin/server', 'server-1.0/lib/x.jar']
        assert get_top_level_directory(names) == 'server-1.0'

    def test_dot_slash_prefixed_names(self) -> None:
        names = ['./', './server-1.0/', './server-1.0/bin/', './server-1.0/bin/server', './server-1.0/lib/x.jar']
        assert get_top_level_directory(names) == 'server-1.0'

    def test_dot_entry_without_slash(self) -> None:
        names = ['.', './server-1.0', './server-1.0/bin/server']
        assert get_top_level_directory(names) == 'server-1.0'

    def test_multiple_roots(self) -> None:
        assert get_top_level_directory(['a/', 'a/file', 'b/', 'b/file']) is None

    def test_multiple_roots_dot_slash_prefixed(self) -> None:
        assert get_top_level_directory(['./', './a/file', './b/file']) is None

    def test_files_at_root(self) -> None:
        assert get_top_level_directory(['server', 'README.md']) is None

    def test_empty(self) -> None:
        assert get_top_level_directory([]) is None
        assert get_top_level_directory(['', './', '.']) is None


class ExtractArchiveTests(TestCase):
    def _extract(self, names: list[str]) -> str | None:
        """Extract a tar.gz archive with given member names and return the returned root relative to the target."""
        with TemporaryDirectory() as tmp:
            archive_path = Path(tmp, 'archive.tar.gz')
            create_tar(archive_path, names)
            target = Path(tmp, 'out')
            target.mkdir()
            result = extract_archive(archive_path, target)
            if result is None:
                return None
            assert result.is_dir()
            assert (result / 'bin' / 'server').is_file()
            return result.relative_to(target).as_posix()

    def test_extract_plain_root(self) -> None:
        assert self._extract(['server-1.0/', 'server-1.0/bin/', 'server-1.0/bin/server']) == 'server-1.0'

    def test_extract_dot_slash_root(self) -> None:
        names = ['./', './server-1.0/', './server-1.0/bin/', './server-1.0/bin/server']
        assert self._extract(names) == 'server-1.0'

    def test_extract_multiple_roots(self) -> None:
        assert self._extract(['./', './a/file', './b/file']) is None
