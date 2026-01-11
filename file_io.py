from typing import Union
import os

def read_file(path: str, mode: str = "r", encoding: str = "utf-8") -> Union[str, bytes]:
    """Read and return the full contents of a file.
    mode: e.g. 'r' or 'rb'. If binary mode is used, encoding is ignored.
    """
    if "b" in mode:
        with open(path, mode) as f:
            return f.read()
    with open(path, mode, encoding=encoding) as f:
        return f.read()

def write_file(path: str, data: Union[str, bytes], mode: str = "w", encoding: str = "utf-8", make_dirs: bool = False) -> None:
    """Write data to a file.
    mode: e.g. 'w' or 'wb'. If make_dirs is True, create parent directories as needed.
    """
    if make_dirs:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    if "b" in mode:
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("binary mode requires bytes-like data")
        with open(path, mode) as f:
            f.write(data)
        return

    # text mode
    if not isinstance(data, str):
        data = str(data)
    with open(path, mode, encoding=encoding) as f:
        f.write(data)
