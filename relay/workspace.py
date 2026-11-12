"""File operations inside the isolated Relay workspace directory."""

import errno
import os
import tempfile
from urllib.parse import unquote

MAX_FILE = 16 * 1024 * 1024


class Download(bytes):
    """An opaque workspace file downloaded as an attachment."""


def file_path(root, suffix):
    if not suffix:
        return root
    parts = unquote(suffix, errors="strict").split("/")
    if any(part in ("", ".", "..") or "\\" in part or "\x00" in part for part in parts):
        raise ValueError("请使用工作目录内的相对路径")
    path = root.joinpath(*parts).resolve()
    if root not in path.parents:
        raise ValueError("路径超出工作目录")
    return path


def list_directory(path):
    entries = []
    for item in sorted(path.iterdir()):
        if not item.is_symlink():
            directory = item.is_dir()
            entries.append({"name": item.name, "type": "directory" if directory else "file",
                            "size": None if directory else item.stat().st_size})
    return {"entries": entries}


def put_file(root, path, content):
    # Stage on the same filesystem, outside the public workspace listing.
    with tempfile.NamedTemporaryFile(dir=str(root.parent), delete=False) as staged:
        temporary = staged.name
        try:
            staged.write(content)
            staged.close()
            os.replace(temporary, str(path))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def remove_path(path):
    if path.is_dir():
        try:
            path.rmdir()
        except OSError as error:
            if error.errno in (errno.ENOTEMPTY, errno.EEXIST):
                raise FileExistsError("目录非空，请先删除目录内容") from error
            raise
    else:
        path.unlink()
