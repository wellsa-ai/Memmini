"""
MemMini CLI

명령줄 인터페이스.
memmini init, add, search, layers, stats 명령어 제공.
"""

import json

import click

from memmini import __version__
from memmini.core.layer_generator import LayerGenerator
from memmini.core.memory_core import MemoryCore
from memmini.storage.file import FileStorage


def _get_memory_core(path: str = "~/.memmini") -> MemoryCore:
    """MemoryCore 인스턴스 생성 헬퍼"""
    storage = FileStorage(base_path=path)
    layer_gen = LayerGenerator()
    return MemoryCore(
        storage=storage,
        layer_generator=layer_gen,
        auto_layer_update=False,  # CLI에서는 수동 제어
    )


@click.group()
@click.version_option(version=__version__, prog_name="memmini")
def cli() -> None:
    """MemMini — L0/L1/L2 계층형 메모리 관리 🧠

    필요한 메모리 계층만 로드해 컨텍스트 토큰을 줄입니다.
    """
    pass


@cli.command()
@click.option(
    "--path",
    default="~/.memmini",
    help="메모리 경로 (기본: ~/.memmini)",
)
def init(path: str) -> None:
    """메모리 저장소 초기화"""
    storage = FileStorage(base_path=path)
    click.echo(f"✅ MemMini 저장소 초기화 완료: {storage.path}")
    click.echo(f"   L0: {storage.l0_file}")
    click.echo(f"   L1: {storage.l1_file}")
    click.echo(f"   L2: {storage.l2_dir}")


@cli.command()
@click.argument("content")
@click.option("--tags", "-t", multiple=True, help="태그")
@click.option("--category", "-c", default=None, help="카테고리")
@click.option("--path", default="~/.memmini", help="메모리 경로")
def add(
    content: str,
    tags: tuple[str, ...],
    category: str | None,
    path: str,
) -> None:
    """메모리 추가

    Examples:
        memmini add "사용자는 Python 개발자"
        memmini add "프로젝트 시작" -t project -t work
    """
    core = _get_memory_core(path)

    metadata: dict[str, object] = {}
    if tags:
        metadata["tags"] = list(tags)
    if category:
        metadata["category"] = category

    memory_id = core.add(content, metadata)
    click.echo(f"✅ 메모리 추가 완료: {memory_id}")


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=5, help="결과 수 (기본: 5)")
@click.option("--path", default="~/.memmini", help="메모리 경로")
def search(query: str, limit: int, path: str) -> None:
    """메모리 검색

    Examples:
        memmini search "Python"
        memmini search "프로젝트" -n 10
    """
    core = _get_memory_core(path)
    results = core.search(query, limit=limit)

    if not results:
        click.echo("검색 결과 없음 🔍")
        return

    click.echo(f"🔍 검색 결과 ({len(results)}건):\n")
    for i, result in enumerate(results, 1):
        content = result.get("content", "")
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        content_preview = content[:100] + "..." if len(content) > 100 else content

        click.echo(f"  {i}. [{result.get('id', '')}]")
        click.echo(f"     {content_preview}")
        click.echo()


@cli.command()
@click.option(
    "--layer",
    "-l",
    default=None,
    type=click.Choice(["L0", "L1", "L2"]),
    help="표시할 계층",
)
@click.option("--path", default="~/.memmini", help="메모리 경로")
def layers(layer: str | None, path: str) -> None:
    """L0/L1/L2 레이어 조회 및 업데이트

    Examples:
        memmini layers           # 레이어 업데이트 + 통계
        memmini layers -l L0     # L0 내용 표시
    """
    core = _get_memory_core(path)

    if layer:
        content = core.retrieve(layer=layer)
        if content:
            click.echo(f"📋 {layer} 내용:\n")
            click.echo(content)
        else:
            click.echo(f"📋 {layer}: (비어있음)")
    else:
        # 레이어 업데이트
        click.echo("🔄 레이어 업데이트 중...")
        result = core.update_layers()
        click.echo("✅ 레이어 업데이트 완료!")
        click.echo(f"   L0: ~{result['L0']} tokens")
        click.echo(f"   L1: ~{result['L1']} tokens")
        click.echo(f"   L2: ~{result['L2']} tokens")
        click.echo(f"   절약: {result['savings']}")


@cli.command()
@click.option("--path", default="~/.memmini", help="메모리 경로")
def stats(path: str) -> None:
    """메모리 통계 조회

    Examples:
        memmini stats
    """
    core = _get_memory_core(path)

    # 메모리 수 계산
    all_memories = core.storage.get_all_raw()
    total = len(all_memories)

    # 레이어 상태
    l0 = core.retrieve(layer="L0")
    l1 = core.retrieve(layer="L1")

    click.echo("📊 MemMini 통계:\n")
    click.echo(f"  총 메모리: {total}개")
    click.echo(f"  L0: {'있음' if l0.strip() else '없음'}")
    click.echo(f"  L1: {'있음' if l1.strip() else '없음'}")
    click.echo(f"  저장소: {getattr(core.storage, 'path', '(unknown)')}")


def main() -> None:
    """CLI 진입점"""
    cli()


if __name__ == "__main__":
    main()
