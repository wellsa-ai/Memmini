"""Vector storage example.

Install vector dependencies first:
    pip install "memmini[vector]"
"""

from tempfile import TemporaryDirectory

from memmini.storage.vector import VectorStorage


def main() -> None:
    with TemporaryDirectory() as tmpdir:
        storage = VectorStorage(persist_directory=tmpdir)
        storage.save("L0 entries are short routing hints.", {"tags": ["L0"]})
        storage.save("L2 keeps the original detailed memory.", {"tags": ["L2"]})

        for result in storage.search("short memory routing", limit=2):
            print(f"{result['id']}: {result['content']}")


if __name__ == "__main__":
    main()
