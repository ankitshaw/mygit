import os
from typing import Optional, Union
import hashlib
import zlib
import sys
import stat

try:
    import file_io
except Exception:
    file_io = None


def _get_git_dir(repo: Optional[str]) -> str:
        """Return the path to the repository's `.git` directory.

        Parameters
        - repo: Optional path. If None, the current working directory is used.
            If `repo` already points to a `.git` directory it is returned unchanged.
            Otherwise the function assumes `repo` is a working-tree path and returns
            `os.path.join(repo, ".git")`.

        Returns
        - Absolute or relative path string that locates the `.git` directory for
            subsequent operations (object storage, refs, etc.).

        Notes
        - This helper does not validate that the returned path actually exists.
        """
    if repo is None:
        return os.path.join(os.getcwd(), ".git")
    # if user passed the .git dir explicitly
    if repo.endswith(os.sep + ".git") or repo.endswith(".git"):
        return repo
    # otherwise assume `repo` is a working-tree path and append `.git`
    return os.path.join(repo, ".git")


def hash_object(data: Union[bytes, str], obj_type: str = "blob", repo: Optional[str] = None) -> str:
     """Create a Git object from `data`, write it to the object database, and
     return its SHA-1 object name.

     Object encoding and storage steps (compatible with Git):
     1. Normalize `data` to bytes (UTF-8 if a `str` is provided).
     2. Build an ASCII header of the form `"<type> <size>\0"` where `<type>` is
         e.g. `blob`, `tree`, or `commit` and `<size>` is the number of data
         bytes.
     3. Concatenate header + data, compute SHA-1 over that payload, compress
         it with zlib, and store it under `.git/objects/ab/cdef...` where `ab`
         are the first two hex characters of the SHA and `cdef...` is the rest.

     Parameters
     - data: bytes or str content to store as an object.
     - obj_type: object type string; commonly `blob`, `tree`, or `commit`.
     - repo: repository working-tree path or `.git` path; if None use cwd.

     Returns
     - 40-character SHA-1 hex string identifying the object.

     Raises
     - Any I/O errors from writing the compressed object file are propagated.
     """
    # normalize data to bytes
    if isinstance(data, str):
        data_bytes = data.encode("utf-8")
    else:
        data_bytes = data

    # build the object header: e.g. b"blob 14\x00"
    header = f"{obj_type} {len(data_bytes)}\0".encode("utf-8")
    # the full payload that Git hashes and compresses
    full = header + data_bytes

    # compute the object name (SHA-1 hex)
    sha = hashlib.sha1(full).hexdigest()

    # target paths under .git/objects/ab/cdef...
    git_dir = _get_git_dir(repo)
    obj_dir = os.path.join(git_dir, "objects", sha[:2])
    obj_path = os.path.join(obj_dir, sha[2:])

    # compress using zlib (same as Git)
    compressed = zlib.compress(full)

    # write the compressed object file; prefer `file_io` helper when available
    if file_io and hasattr(file_io, "write_file"):
        file_io.write_file(obj_path, compressed, mode="wb", make_dirs=True)
    else:
        os.makedirs(obj_dir, exist_ok=True)
        with open(obj_path, "wb") as f:
            f.write(compressed)

    return sha


def find_object(name: str, repo: Optional[str] = None) -> str:
        """Resolve a full object SHA or an unambiguous prefix to the full SHA.

        Behavior
        - If `name` is a full 40-character hex string, directly checks the
            corresponding object file exists and returns the name.
        - If `name` is a shorter prefix, this searches the object database for a
            unique match. Prefixes shorter than two characters are matched by a
            brute-force scan of all object subdirectories. Prefixes of length >= 2
            only examine the relevant two-character subdirectory for efficiency.

        Parameters
        - name: full SHA or prefix (hex string, case-insensitive).
        - repo: repository working-tree path or `.git` path; if None use cwd.

        Returns
        - The full 40-character object SHA string for the unique match.

        Raises
        - FileNotFoundError if no matching object exists.
        - ValueError if the prefix matches multiple objects (ambiguous).
        """
    git_dir = _get_git_dir(repo)
    objects_dir = os.path.join(git_dir, "objects")

    name = name.lower()
    # full 40-char name -> direct lookup
    if len(name) == 40:
        obj_path = os.path.join(objects_dir, name[:2], name[2:])
        if os.path.exists(obj_path):
            return name
        raise FileNotFoundError(name)

    matches = []
    # prefix < 2: brute-force search all object subdirs
    if len(name) < 2:
        for d in os.listdir(objects_dir):
            dirpath = os.path.join(objects_dir, d)
            if not os.path.isdir(dirpath):
                continue
            for f in os.listdir(dirpath):
                if (d + f).startswith(name):
                    matches.append(d + f)
    else:
        # optimize: look up the two-char directory then match the remainder
        dir_prefix = name[:2]
        rest = name[2:]
        dirpath = os.path.join(objects_dir, dir_prefix)
        if not os.path.isdir(dirpath):
            raise FileNotFoundError(name)
        matches = [dir_prefix + f for f in os.listdir(dirpath) if f.startswith(rest)]

    if not matches:
        raise FileNotFoundError(name)
    if len(matches) > 1:
        raise ValueError(f"Ambiguous prefix: {name} matches {len(matches)} objects")
    # return the single matching full hex name
    return matches[0]


def read_object(sha: str, repo: Optional[str] = None) -> tuple[str, bytes]:
        """Read and parse a compressed Git object.

        Steps performed:
        - Resolve `sha` (which may be a short prefix) to a full object name via
            `find_object`.
        - Read the zlib-compressed file from `.git/objects/ab/cdef...`.
        - Decompress and split at the first NUL (0x00) byte to separate the
            header from the object data. The header has the form `b"<type> <size>"`.

        Parameters
        - sha: full SHA or prefix.
        - repo: repository working-tree path or `.git` path; if None use cwd.

        Returns
        - Tuple `(obj_type, data_bytes)`, where `obj_type` is a str like
            `'blob'`, `'tree'`, or `'commit'` and `data_bytes` are the raw payload
            bytes (not the header).

        Raises
        - FileNotFoundError if the object file cannot be found.
        - zlib.error if decompression fails or the file is malformed.
        """
    # resolve prefix -> full sha and object path
    full = find_object(sha, repo)
    git_dir = _get_git_dir(repo)
    obj_path = os.path.join(git_dir, "objects", full[:2], full[2:])

    # read compressed object bytes
    if file_io and hasattr(file_io, "read_file"):
        raw = file_io.read_file(obj_path, mode="rb")
    else:
        with open(obj_path, "rb") as f:
            raw = f.read()

    # decompress and split header/data at the first NUL byte
    decompressed = zlib.decompress(raw)
    header_end = decompressed.find(b"\x00")
    header = decompressed[:header_end]
    data = decompressed[header_end + 1 :]
    obj_type, size_str = header.split(b" ", 1)
    # optional validation could parse int(size_str) and compare to len(data)
    return obj_type.decode("utf-8"), data


def cat_file(mode: str, sha: str, repo: Optional[str] = None) -> None:
        """Minimal implementation of `git cat-file`-like behavior.

        Supported `mode` values:
        - 'type' or '-t': print the object type (e.g. 'blob').
        - 'size' or '-s': print the size in bytes of the object payload.
        - 'pretty' or '-p': pretty-print the object. For blobs/commits this
            writes the raw payload bytes to stdout; for trees it prints human
            readable entries (mode, type, sha, path).
        - 'blob' / 'tree' / 'commit': require the object to be the named type and
            write its raw payload bytes to stdout (binary-safe via
            `sys.stdout.buffer`).

        Parameters
        - mode: chosen output mode (see above).
        - sha: object SHA or prefix.
        - repo: repository working-tree path or `.git` path; if None use cwd.

        Raises
        - ValueError for unsupported modes or type mismatches.
        """
    # fetch object type and raw data bytes
    obj_type, data = read_object(sha, repo)

    # exact-type modes: output the raw object payload directly
    if mode in ("commit", "tree", "blob"):
        if obj_type != mode:
            raise ValueError("expected object type {}, got {}".format(mode, obj_type))
        sys.stdout.buffer.write(data)
        return

    # size and type queries
    if mode in ("-s", "--size", "size"):
        print(len(data))
        return
    if mode in ("-t", "--type", "type"):
        print(obj_type)
        return

    # pretty printing: for blobs/commits print raw bytes; for trees decode entries
    if mode in ("-p", "--pretty", "pretty"):
        if obj_type in ("commit", "blob"):
            # write bytes to stdout (binary-safe)
            sys.stdout.buffer.write(data)
            return
        if obj_type == "tree":
            # tree entries are binary; use read_tree() to parse
            for mode_int, path, sha1 in read_tree(data=data):
                type_str = "tree" if stat.S_ISDIR(mode_int) else "blob"
                print("{:06o} {} {}\t{}".format(mode_int, type_str, sha1, path))
            return
        raise AssertionError(f"unhandled object type {obj_type!r}")

    raise ValueError(f"unexpected mode {mode!r}")


def read_tree(data: bytes):
        """Parse a raw `tree` object payload and yield entries.

        Each entry in a Git tree object has the format:
            <mode (ascii octal)> <path>\0<20-byte binary SHA1>

        The function yields tuples `(mode_int, path, sha_hex)` where `mode_int` is
        the numeric (base-8) mode (e.g. 0o100644), `path` is a decoded string and
        `sha_hex` is the 40-character hex SHA for the referenced object.

        Parameters
        - data: raw bytes payload of a tree object (header already removed).

        Yields
        - (mode_int:int, path:str, sha_hex:str)
        """
    i = 0
    L = len(data)
    while i < L:
        # find space separating mode and path
        j = data.find(b' ', i)
        if j == -1:
            break
        # mode is stored in octal ASCII (e.g. b'100644')
        mode_str = data[i:j]
        # filename is between the space and the NUL byte
        k = data.find(b"\x00", j + 1)
        name = data[j + 1 : k].decode("utf-8")
        # following the NUL is the 20-byte binary SHA1
        sha_raw = data[k + 1 : k + 21]
        sha_hex = sha_raw.hex()
        mode_int = int(mode_str, 8)
        yield mode_int, name, sha_hex
        # advance to the next entry
        i = k + 21


def init(repo_name: str, base_path: Optional[str] = None) -> str:
    """Create a repository folder named `repo_name` and a `.git` file inside it.

    Returns the path to the created repository.
    """
    if base_path is None:
        base_path = os.getcwd()
    repo_path = os.path.join(base_path, repo_name)
    os.makedirs(repo_path, exist_ok=True)

    git_dir_path = os.path.join(repo_path, ".git")

    # create standard git directory structure
    dirs = [
        "objects",
        "refs/heads",
        "refs/tags",
        "hooks",
        "info",
    ]
    for d in dirs:
        os.makedirs(os.path.join(git_dir_path, d), exist_ok=True)

    # minimal files
    head_path = os.path.join(git_dir_path, "HEAD")
    head_content = "ref: refs/heads/master\n"

    config_path = os.path.join(git_dir_path, "config")
    config_content = (
        "[core]\n"
        "\trepositoryformatversion = 0\n"
        "\tfilemode = true\n"
        "\tbare = false\n"
    )

    description_path = os.path.join(git_dir_path, "description")
    description_content = (
        "Unnamed repository; edit this file 'description' to name the repository.\n"
    )

    if file_io and hasattr(file_io, "write_file"):
        file_io.write_file(head_path, head_content, mode="w", make_dirs=True)
        file_io.write_file(config_path, config_content, mode="w", make_dirs=True)
        file_io.write_file(description_path, description_content, mode="w", make_dirs=True)
    else:
        with open(head_path, "w", encoding="utf-8") as f:
            f.write(head_content)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_content)
        with open(description_path, "w", encoding="utf-8") as f:
            f.write(description_content)

    return repo_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Simple mygit CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize a repository")
    init_parser.add_argument("repo", help="Repository name to create")
    init_parser.add_argument("--path", "-p", default=None, help="Base path to create the repo (defaults to cwd)")

    cat_parser = subparsers.add_parser("cat-file", help="Display repository object contents")
    cat_group = cat_parser.add_mutually_exclusive_group(required=True)
    cat_group.add_argument("-p", "--pretty", action="store_true", help="pretty-print object")
    cat_group.add_argument("-t", "--type", action="store_true", help="show object type")
    cat_group.add_argument("-s", "--size", action="store_true", help="show object size")
    cat_group.add_argument("--blob", action="store_true", help="expect blob and output raw data")
    cat_group.add_argument("--tree", action="store_true", help="expect tree and output raw data")
    cat_group.add_argument("--commit", action="store_true", help="expect commit and output raw data")
    cat_parser.add_argument("sha", help="Object sha (or prefix)")
    cat_parser.add_argument("--path", "-P", default=None, help="Repository base path (defaults to cwd)")

    args = parser.parse_args()

    if args.command == "init":
        path = init(args.repo, base_path=args.path)
        print(f"Created repository at: {path}")
    elif args.command == "cat-file":
        if args.pretty:
            mode = "pretty"
        elif args.type:
            mode = "type"
        elif args.size:
            mode = "size"
        elif args.blob:
            mode = "blob"
        elif args.tree:
            mode = "tree"
        elif args.commit:
            mode = "commit"
        else:
            raise SystemExit("No mode specified for cat-file")

        cat_file(mode, args.sha, repo=args.path)
