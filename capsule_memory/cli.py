"""
CapsuleMemory CLI — full-featured command-line interface using typer + rich.

Commands:
    capsule ingest    — Ingest a conversation turn into a session
    capsule seal      — Seal a session into a persistent capsule
    capsule list      — List capsules with rich table output
    capsule show      — Show full capsule details
    capsule export    — Export capsule to file
    capsule import    — Import capsule from file
    capsule merge     — Merge multiple capsules
    capsule skills    — List skill/hybrid capsules
    capsule recall    — Recall memories for a query
    capsule serve     — Start REST API Server
    capsule mcp       — Start MCP Server
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from capsule_memory.api import CapsuleMemory

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="capsule-memory",
    help="CapsuleMemory CLI — User-sovereign AI memory capsule system",
    no_args_is_help=True,
)

console = Console()
logger = logging.getLogger(__name__)

# ─── Global options via callback ────────────────────────────────────────────

_storage_path: str = os.getenv("CAPSULE_STORAGE_PATH", "~/.capsules")
_default_user: str = os.getenv("CAPSULE_DEFAULT_USER", "default")


@app.callback()
def main(
    storage: str = typer.Option(
        os.getenv("CAPSULE_STORAGE_PATH", "~/.capsules"),
        "--storage",
        help="Storage directory path",
    ),
    user: str = typer.Option(
        os.getenv("CAPSULE_DEFAULT_USER", "default"),
        "--user",
        help="Default user ID",
    ),
) -> None:
    """CapsuleMemory CLI — manage AI memory capsules."""
    global _storage_path, _default_user
    _storage_path = storage
    _default_user = user


def _get_cm() -> "CapsuleMemory":
    """Create a CapsuleMemory instance with current settings."""
    from capsule_memory.api import CapsuleMemory, CapsuleMemoryConfig

    config = CapsuleMemoryConfig.from_env()
    config.storage_path = _storage_path
    return CapsuleMemory(config=config, on_skill_trigger=lambda e: None)


def _run(coro: Any) -> Any:
    """Run an async coroutine from sync context."""
    return asyncio.run(coro)


# ─── In-memory session state for CLI workflow ─────────────────────────────────
_cli_sessions: dict[str, Any] = {}  # session_id → SessionTracker


def _get_or_create_cli_session(
    cm: "CapsuleMemory", session_id: str, user_id: str
) -> Any:
    """Get or create a SessionTracker for CLI ingest/seal workflow."""
    if session_id in _cli_sessions and _cli_sessions[session_id].state.is_active:
        return _cli_sessions[session_id]
    ctx = cm.session(user_id=user_id, session_id=session_id)
    tracker = ctx._tracker
    tracker.config.auto_seal_on_exit = False
    _cli_sessions[session_id] = tracker
    return tracker


# ─── ingest ────────────────────────────────────────────────────────────────

@app.command("ingest")
def ingest(
    user_message: str = typer.Argument(..., help="User message text"),
    assistant_response: str = typer.Argument(..., help="Assistant response text"),
    session: str = typer.Option("cli_session", "--session", "-s", help="Session ID"),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="User ID"),
) -> None:
    """Ingest a conversation turn into a session."""
    cm = _get_cm()
    user_id = user or _default_user
    tracker = _get_or_create_cli_session(cm, session, user_id)
    turn = _run(tracker.ingest(user_message, assistant_response))
    console.print(
        f"[green]Ingested turn {turn.turn_id}[/green] into session [cyan]{session}[/cyan] "
        f"({len(tracker.state.turns)} total turns)"
    )


# ─── seal ──────────────────────────────────────────────────────────────────

@app.command("seal")
def seal(
    session: str = typer.Option("cli_session", "--session", "-s", help="Session ID to seal"),
    title: str = typer.Option("", "--title", "-t", help="Capsule title"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Tag (repeatable via comma-separated)"),
) -> None:
    """Seal a session into a persistent memory capsule."""
    if session not in _cli_sessions:
        console.print(f"[red]No active session '{session}'. Ingest turns first.[/red]")
        raise typer.Exit(1)

    tracker = _cli_sessions[session]
    if not tracker.state.is_active:
        console.print(f"[red]Session '{session}' is already sealed.[/red]")
        raise typer.Exit(1)

    tags = [t.strip() for t in tag.split(",")] if tag else []
    capsule = _run(tracker.seal(title=title, tags=tags))
    del _cli_sessions[session]

    console.print(f"[green]Sealed![/green] Capsule [cyan]{capsule.capsule_id[:16]}[/cyan]")
    console.print(
        f"[dim]Type: {capsule.capsule_type.value} | "
        f"Turns: {capsule.metadata.turn_count} | "
        f"Title: {capsule.metadata.title or '(untitled)'}[/dim]"
    )


# ─── list ───────────────────────────────────────────────────────────────────

@app.command("list")
def list_capsules(
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Filter by user ID"),
    type: Optional[str] = typer.Option(
        None, "--type", "-t", help="Filter by type (memory|skill|hybrid|context)"
    ),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter by tag"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
) -> None:
    """List capsules with a formatted table."""
    from capsule_memory.models.capsule import CapsuleType as CT

    cm = _get_cm()
    user_id = user or _default_user
    capsule_type = CT(type) if type else None
    tags = [tag] if tag else None

    capsules = _run(
        cm.store.list(user_id=user_id, capsule_type=capsule_type, tags=tags, limit=limit)
    )

    if not capsules:
        console.print("[dim]No capsules found.[/dim]")
        return

    table = Table(title=f"Capsules ({len(capsules)} results)")
    table.add_column("ID", style="cyan", max_width=12)
    table.add_column("Type", style="green")
    table.add_column("Title", style="white", max_width=30)
    table.add_column("Tags", style="yellow", max_width=20)
    table.add_column("Sealed At", style="dim")
    table.add_column("Turns", justify="right")

    for c in capsules:
        sealed = (
            c.lifecycle.sealed_at.strftime("%Y-%m-%d %H:%M")
            if c.lifecycle.sealed_at
            else "-"
        )
        table.add_row(
            c.capsule_id[:12],
            c.capsule_type.value,
            c.metadata.title[:30] or "(untitled)",
            ", ".join(c.metadata.tags[:3]),
            sealed,
            str(c.metadata.turn_count),
        )

    console.print(table)


# ─── show ───────────────────────────────────────────────────────────────────

@app.command("show")
def show_capsule(
    capsule_id: str = typer.Argument(..., help="Capsule ID to display"),
) -> None:
    """Show full capsule details in a panel."""
    cm = _get_cm()
    try:
        capsule = _run(cm.store.get(capsule_id))
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    # Build detail text
    lines: list[str] = []
    lines.append(f"[bold]ID:[/bold]       {capsule.capsule_id}")
    lines.append(f"[bold]Type:[/bold]     {capsule.capsule_type.value}")
    lines.append(f"[bold]Status:[/bold]   {capsule.lifecycle.status.value}")
    lines.append(f"[bold]User:[/bold]     {capsule.identity.user_id}")
    lines.append(f"[bold]Session:[/bold]  {capsule.identity.session_id}")
    lines.append(f"[bold]Platform:[/bold] {capsule.identity.origin_platform}")
    lines.append(f"[bold]Title:[/bold]    {capsule.metadata.title}")
    lines.append(f"[bold]Tags:[/bold]     {', '.join(capsule.metadata.tags)}")
    lines.append(f"[bold]Turns:[/bold]    {capsule.metadata.turn_count}")

    created = capsule.lifecycle.created_at.strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"[bold]Created:[/bold]  {created}")

    if capsule.lifecycle.sealed_at:
        sealed = capsule.lifecycle.sealed_at.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"[bold]Sealed:[/bold]   {sealed}")

    lines.append(f"[bold]Checksum:[/bold] {capsule.integrity.checksum[:16]}...")

    # Payload summary
    lines.append("")
    lines.append("[bold]Payload Summary:[/bold]")
    if capsule.capsule_type.value == "memory":
        facts = capsule.payload.get("facts", [])
        summary = capsule.payload.get("context_summary", "")[:100]
        lines.append(f"  Facts: {len(facts)}")
        lines.append(f"  Summary: {summary}")
    elif capsule.capsule_type.value == "skill":
        lines.append(f"  Skill: {capsule.payload.get('skill_name', 'N/A')}")
        lines.append(f"  Trigger: {capsule.payload.get('trigger_pattern', '')[:80]}")
    elif capsule.capsule_type.value == "hybrid":
        mem = capsule.payload.get("memory", {})
        skills = capsule.payload.get("skills", [])
        lines.append(f"  Facts: {len(mem.get('facts', []))}")
        lines.append(f"  Skills: {len(skills)}")

    panel = Panel("\n".join(lines), title=f"Capsule: {capsule_id[:16]}", border_style="cyan")
    console.print(panel)


# ─── export ─────────────────────────────────────────────────────────────────

@app.command("export")
def export_capsule(
    capsule_id: str = typer.Argument(..., help="Capsule ID to export"),
    output_path: str = typer.Argument(..., help="Output file path"),
    format: str = typer.Option(
        "json", "--format", "-f", help="Export format (json|universal|prompt|msgpack)"
    ),
    encrypt: bool = typer.Option(False, "--encrypt", help="Encrypt the output"),
    passphrase: str = typer.Option("", "--passphrase", "-p", help="Encryption passphrase"),
) -> None:
    """Export a capsule to file."""
    cm = _get_cm()
    try:
        result = _run(
            cm.export_capsule(
                capsule_id,
                output_path,
                format=format,  # type: ignore[arg-type]
                encrypt=encrypt,
                passphrase=passphrase,
            )
        )
        size = result.stat().st_size
        console.print(f"[green]Exported to:[/green] {result}")
        console.print(f"[dim]Format: {format} | Size: {size:,} bytes[/dim]")
    except Exception as e:
        console.print(f"[red]Export failed: {e}[/red]")
        raise typer.Exit(1)


# ─── import ─────────────────────────────────────────────────────────────────

@app.command("import")
def import_capsule(
    file_path: str = typer.Argument(..., help="File path to import"),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Target user ID"),
    passphrase: str = typer.Option("", "--passphrase", "-p", help="Decryption passphrase"),
) -> None:
    """Import a capsule from file."""
    cm = _get_cm()
    user_id = user or _default_user
    try:
        capsule = _run(cm.import_capsule(file_path, user_id, passphrase))
        console.print(f"[green]Imported:[/green] {capsule.capsule_id}")
        console.print(f"[dim]Type: {capsule.capsule_type.value} | Title: {capsule.metadata.title}[/dim]")
    except Exception as e:
        console.print(f"[red]Import failed: {e}[/red]")
        raise typer.Exit(1)


# ─── merge ──────────────────────────────────────────────────────────────────

@app.command("merge")
def merge_capsules(
    id1: str = typer.Argument(..., help="First capsule ID"),
    id2: str = typer.Argument(..., help="Second capsule ID"),
    title: str = typer.Option("", "--title", "-t", help="Title for merged capsule"),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="User ID"),
) -> None:
    """Merge two capsules into a new one."""
    cm = _get_cm()
    try:
        merged = _run(
            cm.store.merge(
                capsule_ids=[id1, id2],
                title=title,
                user_id=user,
            )
        )
        console.print(f"[green]Merged:[/green] {merged.capsule_id}")
        console.print(
            f"[dim]Type: {merged.capsule_type.value} | "
            f"Turns: {merged.metadata.turn_count}[/dim]"
        )
    except Exception as e:
        console.print(f"[red]Merge failed: {e}[/red]")
        raise typer.Exit(1)


# ─── skills ─────────────────────────────────────────────────────────────────

@app.command("skills")
def list_skills(
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Filter by user ID"),
) -> None:
    """List all skill and hybrid capsules."""
    from capsule_memory.models.capsule import CapsuleType as CT

    cm = _get_cm()
    user_id = user or _default_user

    skill_capsules = _run(
        cm.store.list(user_id=user_id, capsule_type=CT.SKILL, limit=50)
    )
    hybrid_capsules = _run(
        cm.store.list(user_id=user_id, capsule_type=CT.HYBRID, limit=50)
    )

    all_skills = skill_capsules + hybrid_capsules
    if not all_skills:
        console.print("[dim]No skill capsules found.[/dim]")
        return

    table = Table(title=f"Skills ({len(all_skills)} capsules)")
    table.add_column("ID", style="cyan", max_width=12)
    table.add_column("Type", style="green")
    table.add_column("Skill Name", style="bold white", max_width=30)
    table.add_column("Trigger", style="yellow", max_width=40)

    for c in all_skills:
        if c.capsule_type == CT.SKILL:
            skill_name = c.payload.get("skill_name", "N/A")
            trigger = c.payload.get("trigger_pattern", "")[:40]
        else:
            skills_list = c.payload.get("skills", [])
            if skills_list:
                skill_name = skills_list[0].get("skill_name", "N/A")
                trigger = skills_list[0].get("trigger_pattern", "")[:40]
            else:
                skill_name = "(hybrid, no skills)"
                trigger = ""

        table.add_row(
            c.capsule_id[:12],
            c.capsule_type.value,
            skill_name[:30],
            trigger,
        )

    console.print(table)


# ─── recall ─────────────────────────────────────────────────────────────────

@app.command("recall")
def recall_memories(
    query: str = typer.Argument(..., help="Search query"),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="User ID"),
    top_k: int = typer.Option(3, "--top-k", "-k", help="Number of results"),
) -> None:
    """Recall relevant memories for a query."""
    cm = _get_cm()
    user_id = user or _default_user

    try:
        result = _run(cm.recall(query, user_id=user_id, top_k=top_k))
    except Exception as e:
        console.print(f"[red]Recall failed: {e}[/red]")
        raise typer.Exit(1)

    prompt = result.get("prompt_injection", "")
    facts = result.get("facts", [])
    sources = result.get("sources", [])

    console.print(Panel(prompt, title="Recalled Context", border_style="green"))
    console.print(f"[dim]Facts: {len(facts)} | Sources: {len(sources)}[/dim]")


# ─── serve ──────────────────────────────────────────────────────────────────

@app.command("serve")
def serve(
    port: int = typer.Option(8000, "--port", "-p", help="Server port"),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Server host"),
    storage: Optional[str] = typer.Option(None, "--storage", help="Storage path"),
) -> None:
    """Start the REST API Server."""
    from capsule_memory.server.rest_api import run_server

    storage_path = storage or _storage_path
    console.print(f"[bold]Starting REST API Server[/bold] at {host}:{port}")
    console.print(f"[dim]Storage: {storage_path}[/dim]")
    run_server(host=host, port=port, storage_path=storage_path)


# ─── mcp ────────────────────────────────────────────────────────────────────

@app.command("mcp")
def mcp(
    storage: Optional[str] = typer.Option(None, "--storage", help="Storage path"),
) -> None:
    """Start the MCP Server (for Claude Code / Claude Desktop integration)."""
    from capsule_memory.server.mcp_server import main as mcp_main

    if storage:
        os.environ["CAPSULE_STORAGE_PATH"] = storage
    # Do NOT print to stdout — MCP uses stdout for JSON-RPC protocol.
    import sys
    print("Starting MCP Server...", file=sys.stderr)
    mcp_main()


# ─── version ────────────────────────────────────────────────────────────────

@app.command("version")
def version() -> None:
    """Show CapsuleMemory version."""
    from capsule_memory import __version__

    console.print(f"capsule-memory {__version__}")


if __name__ == "__main__":
    app()
