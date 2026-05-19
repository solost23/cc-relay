import sys


def main() -> None:
    args = sys.argv[1:]

    if not args:
        from cc_relay.server import main as serve
        serve()
        return

    cmd = args[0]

    if cmd == "--install":
        from cc_relay.installer import install
        install()

    elif cmd == "--uninstall":
        from cc_relay.installer import uninstall
        uninstall()

    elif cmd == "--reset":
        if len(args) < 2:
            print("Usage: cc-relay --reset <action_type>", file=sys.stderr)
            sys.exit(1)
        from cc_relay.db import init_db, reset_action_type
        init_db()
        count = reset_action_type(args[1])
        print(f"✓ Reset '{args[1]}': deleted {count} decision(s).")

    elif cmd == "--history":
        if len(args) < 2:
            print("Usage: cc-relay --history <action_type> [limit]", file=sys.stderr)
            sys.exit(1)
        import json
        from cc_relay.db import init_db, get_recent_decisions
        init_db()
        limit = int(args[2]) if len(args) >= 3 else 20
        decisions = get_recent_decisions(args[1], limit)
        print(json.dumps(decisions, indent=2, default=str))

    elif cmd == "hook" and len(args) >= 2:
        from cc_relay.db import init_db
        init_db()
        subcommand = args[1]
        if subcommand == "pre":
            from cc_relay.hook import run_pre_tool_use
            run_pre_tool_use()
        elif subcommand == "post":
            from cc_relay.hook import run_post_tool_use
            run_post_tool_use()
        elif subcommand == "stop":
            from cc_relay.hook import run_stop
            run_stop()
        else:
            print(f"Unknown hook subcommand: {subcommand}", file=sys.stderr)
            sys.exit(1)

    else:
        print("Usage: cc-relay [--install | --uninstall | --reset <type> | --history <type> [limit] | hook pre|post|stop]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
