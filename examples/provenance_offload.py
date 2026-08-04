"""Source drill-down and symbolic offload example."""

from tempfile import TemporaryDirectory

from memmini import open_memory


def main() -> None:
    with TemporaryDirectory() as tmpdir:
        memory = open_memory(tmpdir, auto_layer_update=False)
        memory.add(
            "Checkout rollback requires draining the worker queue first.",
            metadata={"scenario": "checkout", "tags": ["runbook"]},
        )

        result = memory.search("rollback", limit=1)[0]
        source = memory.resolve_source_ref(result["source_ref"])
        print(source["content"])

        raw_trace = "\n".join(
            f"step {i}: worker queue diagnostic output" for i in range(20)
        )
        offloaded = memory.offload_context("checkout diagnostic trace", raw_trace)
        print(offloaded["mermaid"])

        print(memory.extract_scenarios()[0]["scenario"])


if __name__ == "__main__":
    main()
