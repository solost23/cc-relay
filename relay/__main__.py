import sys


def main() -> None:
    args = sys.argv[1:]

    if not args:
        # Default: start MCP server
        from relay.server import main as serve
        serve()
        return

    cmd = args[0]

    if cmd == "--install":
        from relay.installer import install
        install()

    elif cmd == "--uninstall":
        from relay.installer import uninstall
        uninstall()

    elif cmd == "hook" and len(args) >= 2:
        from relay.db import init_db
        init_db()
        subcommand = args[1]
        if subcommand == "pre":
            from relay.hook import run_pre_tool_use
            run_pre_tool_use()
        elif subcommand == "post":
            from relay.hook import run_post_tool_use
            run_post_tool_use()
        else:
            print(f"Unknown hook subcommand: {subcommand}", file=sys.stderr)
            sys.exit(1)

    else:
        print(f"Usage: relay [--install | --uninstall | hook pre | hook post]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
