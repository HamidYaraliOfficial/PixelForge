#!/usr/bin/env python3
"""
PixelForge - Universal Intelligent Image Compression Studio
================================================================

Entry point. Launches the GUI by default; delegates to the CLI when
subcommands are given (e.g. `python main.py compress image.jpg`).

Usage:
    python main.py                 -> launches the GUI
    python main.py gui             -> launches the GUI
    python main.py compress ...    -> runs the CLI (see `python main.py --help`)
"""
import sys

CLI_COMMANDS = {
    "compress", "auto", "batch", "analyze", "benchmark", "convert",
    "target", "library-scan", "formats", "presets", "history", "report",
    "--help", "-h",
}


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] == "gui":
        from gui.app import run_gui
        return run_gui()
    if args[0] in CLI_COMMANDS or any(a in CLI_COMMANDS for a in args):
        from cli.main import main as cli_main
        return cli_main(args)
    # Unknown first token: fall through to CLI so argparse prints proper usage/help.
    from cli.main import main as cli_main
    return cli_main(args)


if __name__ == "__main__":
    sys.exit(main())
