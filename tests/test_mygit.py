import io
import os
import sys
import tempfile
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import mygit


def _capture_stdout_bytes(func, *args, **kwargs):
    class C:
        def __init__(self):
            self.buffer = io.BytesIO()
        def write(self, s):
            if isinstance(s, str):
                self.buffer.write(s.encode())
            else:
                self.buffer.write(s)
    old = sys.stdout
    fake = C()
    sys.stdout = fake
    try:
        func(*args, **kwargs)
    finally:
        sys.stdout = old
    return fake.buffer.getvalue()


def test_init_creates_git_structure(tmp_path):
    root = str(tmp_path)
    repo_name = "test-repo"
    repo_path = mygit.init(repo_name, base_path=root)
    git_dir = Path(repo_path) / ".git"
    assert git_dir.exists()
    assert (git_dir / "objects").is_dir()
    assert (git_dir / "refs" / "heads").is_dir()
    assert (git_dir / "HEAD").is_file()


def test_hash_and_read_and_find(tmp_path):
    root = str(tmp_path)
    repo_name = "test-repo-obj"
    repo_path = mygit.init(repo_name, base_path=root)
    data = b"hello world\n"
    sha = mygit.hash_object(data, obj_type="blob", repo=repo_path)

    # object file exists
    obj_path = Path(repo_path) / ".git" / "objects" / sha[:2] / sha[2:]
    assert obj_path.exists()

    # read_object returns correct type and data
    obj_type, read_data = mygit.read_object(sha, repo=repo_path)
    assert obj_type == "blob"
    assert read_data == data

    # find by prefix
    found = mygit.find_object(sha[:6], repo=repo_path)
    assert found == sha


def test_cat_file_modes(tmp_path):
    root = str(tmp_path)
    repo_name = "test-repo-cat"
    repo_path = mygit.init(repo_name, base_path=root)
    data = b"Line1\nLine2\n"
    sha = mygit.hash_object(data, obj_type="blob", repo=repo_path)

    # type
    out = _capture_stdout_bytes(mygit.cat_file, "type", sha, repo=repo_path)
    assert out.decode().strip() == "blob"

    # size
    out = _capture_stdout_bytes(mygit.cat_file, "size", sha, repo=repo_path)
    assert out.decode().strip() == str(len(data))

    # pretty (blob -> raw bytes)
    out = _capture_stdout_bytes(mygit.cat_file, "pretty", sha, repo=repo_path)
    assert out == data

    # raw blob
    out = _capture_stdout_bytes(mygit.cat_file, "blob", sha, repo=repo_path)
    assert out == data
