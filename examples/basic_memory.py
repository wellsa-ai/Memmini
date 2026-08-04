"""Basic MemMini file-backed memory example."""

from tempfile import TemporaryDirectory

from memmini import open_memory


def main() -> None:
    with TemporaryDirectory() as tmpdir:
        memory = open_memory(tmpdir, auto_layer_update=False)

        memory.add(
            "MemMini uses L0/L1/L2 layers to avoid loading full memory every time.",
            metadata={"tags": ["oss", "memory"], "category": "note"},
        )
        memory.update_layers()

        print("L0")
        print(memory.retrieve(layer="L0"))
        print()
        print("Search")
        for item in memory.search("layers", limit=3):
            print(f"- {item['content']}")


if __name__ == "__main__":
    main()
