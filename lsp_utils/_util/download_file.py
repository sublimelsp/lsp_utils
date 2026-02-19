from __future__ import annotations

from shutil import copyfileobj
from typing import TYPE_CHECKING
from urllib.request import urlopen
from zipfile import ZipFile
import tarfile

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    'download_file',
    'extract_archive',
]


def download_file(url: str, target_path: Path) -> None:
    """Download given URL to the specified target file path."""
    with urlopen(url) as response, target_path.open('wb') as out_file:  # noqa: S310
        copyfileobj(response, out_file)


def extract_archive(archive_file: Path, target_directory: Path) -> Path:
    """
    Extract all files from an archive.

    :param archive_file: Path to the archive file to extract.
    :param target_directory: Directory where files will be extracted.
    :return: Path to the extracted directory. If the archive contains a single
             root directory, the returned path will include that directory.
    """
    archive_name = archive_file.name
    if archive_name.endswith('.zip'):
        with ZipFile(archive_file) as archive:
            return extract_files_from_archive(archive, target_directory)
    elif archive_name.endswith(('.tar.gz', 'tgz', '.tar.bz2', '.tar.xz')):
        with tarfile.open(archive_file, 'r:*') as archive:
            return extract_files_from_archive(archive, target_directory)
    else:
        msg = f'Unsupported archive "{archive_name}"'
        raise Exception(msg)


def extract_files_from_archive(archive: ZipFile | tarfile.TarFile, target_directory: Path) -> Path:
    names = archive.namelist() if isinstance(archive, ZipFile) else archive.getnames()
    bad_members = [x for x in names if x.startswith(('/', '..'))]
    if bad_members:
        msg = f'archive appears to be malicious, bad filenames: {bad_members}'
        raise Exception(msg)
    topdir_name = get_top_level_directory(names)
    archive.extractall(str(target_directory))  # noqa: S202
    if topdir_name:
        return target_directory / topdir_name
    return target_directory


def get_top_level_directory(names: list[str]) -> str | None:
    """
    Check if all files in a list are contained within a parent directory.

    Returns str | None: Common parent name if present.
    """
    # Filter out directory entries and get top-level paths.
    top_levels: set[str] = set()
    for name in names:
        # Skip empty entries
        if not name:
            continue
        # Get the first component of the path
        top_level = name.split('/')[0]
        top_levels.add(top_level)

    # If there's only one top-level entry, all files share a parent
    return top_levels.pop() if len(top_levels) == 1 else None
