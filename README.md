# mygit

**Step 1: Initialize a repository (create .git directory)**

Use the included `mygit.py` to create a minimal repository layout (this is a teaching example, not a full Git implementation):

- Create a repo named `demo-repo` in the current directory:

```bash
python3 mygit.py init demo-repo
```

- What this does:
	- Creates the `demo-repo` folder.
	- Creates a `.git` directory inside it with these minimal entries:
		- Directories: `objects`, `refs/heads`, `refs/tags`, `hooks`, `info`
		- Files: `HEAD` (points to `refs/heads/master`), `config` (basic core settings), and `description`.

- Example `.git` tree produced:

```
demo-repo/
└── .git/
		├── HEAD
		├── config
		├── description
		├── hooks/
		├── info/
		├── objects/
		└── refs/
				├── heads/
				└── tags/
```

This is Step 1 of a tutorial to build Git from scratch. Next steps would cover writing objects into `objects/`, updating references in `refs/`, and implementing plumbing commands (hashing objects, creating commits, etc.).

**Step 2: Objects — hashing and storing object data**

Git stores content (blobs, trees, commits) as objects in the `.git/objects` database. Each object is stored as:

- A header: `<type> <size>\0` (ASCII)
- The raw data bytes
- The header+data are SHA-1 hashed, then zlib-compressed and written under `.git/objects/ab/cdef...` where `ab` are the first two hex characters of the hash.

Using the included code:

- `mygit.hash_object(data, obj_type='blob', repo=...)` — builds the header, computes the SHA-1, compresses, and writes the object file; returns the object SHA.
- `mygit.find_object(prefix, repo=...)` — find an object by full SHA or unique prefix.
- `mygit.read_object(sha, repo=...)` — read and decompress an object, returning `(type, data_bytes)`.
- `mygit.cat_file(mode, sha, repo=...)` — print object information or contents; supported `mode`s include `type`, `size`, `pretty`, and exact-type outputs `blob`, `tree`, `commit`.

Example (create a blob and show it):

```bash
python3 mygit.py init demo-repo
sha=$(python3 - <<'PY'
import mygit
print(mygit.hash_object(b"Hello\n", "blob", repo="demo-repo"))
PY
)
python3 mygit.py cat-file -t "$sha" --path demo-repo   # show type
python3 mygit.py cat-file -s "$sha" --path demo-repo   # show size
python3 mygit.py cat-file --pretty "$sha" --path demo-repo  # pretty-print
```

Step 3 will cover object types (`tree` and `commit`) and how to create and link them together.