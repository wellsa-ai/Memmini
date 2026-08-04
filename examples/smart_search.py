"""Smart search example with positive and negative keyword extraction."""

from tempfile import TemporaryDirectory

from memmini import open_memory
from memmini.logic.query_analyzer import QueryAnalyzer


def main() -> None:
    with TemporaryDirectory() as tmpdir:
        memory = open_memory(tmpdir, auto_layer_update=False)
        memory.add("Project A succeeded with a small memory footprint.")
        memory.add("Project B failed because the prompt loaded too much context.")

        analyzer = QueryAnalyzer()
        analyzed = analyzer.analyze("Project succeeded. failed entries 제외")

        results = memory.search(
            "Project",
            positive=["succeeded"],
            negative=analyzed["negative"] or ["failed"],
        )
        for result in results:
            print(result["content"])


if __name__ == "__main__":
    main()
