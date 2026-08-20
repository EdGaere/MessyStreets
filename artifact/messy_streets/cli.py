"""messy-streets — reproduce the MESSY STREETS results.

Stdlib only. Every verb takes --json, and every verb writes only inside --out.

Exit codes are distinct so continuous integration can assert on them:
    0  reproduced / all checks passed
    1  mismatch against the published result
    2  environment or data-integrity failure
    3  this layer is not available here
"""

from argparse import ArgumentParser, Namespace, RawDescriptionHelpFormatter
from json import dumps
from typing import List

from messy_streets import __version__, doctor, paths, verbs

EXIT_OK, EXIT_MISMATCH, EXIT_ENVIRONMENT, EXIT_UNAVAILABLE = 0, 1, 2, 3

STATUS_MARK = {"ok": "ok", "warn": "warn", "fail": "FAIL", "skip": "--"}


def _epilog() -> str:
    lines = ["commands:"]
    for verb in verbs.load().values():
        pending = "" if verb.implemented else f"   [slice {verb.slice}, not built yet]"
        layer = f"{verb.layer:<3}" if verb.layer != "-" else "   "
        lines.append(f"  {verb.name:<10}{layer} {verb.description}{pending}")
    lines.append("")
    lines.append("Layers: L0 released data · L1 cached predictions · L2 benchmark slices")
    lines.append("        L3 live geocoders (needs API keys) · L4 dataset construction")
    return "\n".join(lines)


def _print_report(checks: List[doctor.Check]) -> None:
    width = max(len(c.name) for c in checks) + 2
    group = None
    for check in checks:
        if check.group != group:
            group = check.group
            print(f"\n{group}")
        mark = STATUS_MARK[check.status]
        print(f"  {check.name:<{width}} {mark:<5} {check.detail}")


def cmd_doctor(args: Namespace) -> int:
    checks = doctor.run()
    failed = [c for c in checks if c.failed]
    warned = [c for c in checks if c.status == "warn"]

    if args.json:
        print(dumps({
            "artefact_version": __version__,
            "root": str(paths.root()),
            "checks": [c._asdict() for c in checks],
            "summary": {
                "total": len(checks),
                "failed": len(failed),
                "warned": len(warned),
            },
            "exit_code": EXIT_ENVIRONMENT if failed else EXIT_OK,
        }, indent=2))
        return EXIT_ENVIRONMENT if failed else EXIT_OK

    print(f"MESSY STREETS artefact v{__version__}")
    print(f"root: {paths.root()}")
    _print_report(checks)

    print()
    if failed:
        print(f"{len(failed)} check(s) FAILED — this environment cannot reproduce the results.")
        for check in failed:
            print(f"  {check.group}/{check.name}: {check.detail}")
        return EXIT_ENVIRONMENT

    if warned:
        print(f"ready, with {len(warned)} warning(s).")
        print("Warnings are expected outside the container; inside it they should be clear.")
    else:
        print("ready.")
    return EXIT_OK


def cmd_smoke(args: Namespace) -> int:
    from messy_streets import smoke
    return smoke.run(as_json=args.json, verbose=args.verbose)


def cmd_tables(args: Namespace) -> int:
    from messy_streets import tables
    return tables.run(as_json=args.json, verbose=args.verbose)


def cmd_stats(args: Namespace) -> int:
    from messy_streets import stats
    return stats.run(as_json=args.json, verbose=args.verbose)


def cmd_inspect(args: Namespace) -> int:
    from messy_streets import inspect_tier
    return inspect_tier.run(tier=args.tier, count=args.n, contains=args.contains,
                            missing=args.missing, as_json=args.json)


def cmd_sample(args: Namespace) -> int:
    from messy_streets import sample
    return sample.run(as_json=args.json, verbose=args.verbose, limit=args.limit)


def cmd_pipeline(args: Namespace) -> int:
    from messy_streets import pipeline
    return pipeline.run(action=args.action, stage=args.stage,
                        as_json=args.json, verbose=args.verbose)


def cmd_shell(args: Namespace) -> int:
    """A prompt with the artefact importable.

    In the container the entrypoint intercepts `shell` before the CLI sees it,
    so this is the native path: a login shell in the repository root with
    PYTHONPATH already pointing at the vendored tree.
    """
    from os import environ, execvp
    from messy_streets import paths

    environment_note = (
        f"MESSY STREETS artefact v{__version__}\n"
        f"  root        {paths.root()}\n"
        f"  PYTHONPATH  {paths.src()}\n"
        f"  data        {paths.data()}\n"
        "\nThe vendored closure is importable: try\n"
        "  python3 -c 'from messy_streets import tiers; print(next(tiers.read(\"gold\")))'\n"
    )
    print(environment_note, flush=True)

    environ["PYTHONPATH"] = str(paths.src())
    environ["MS_ROOT"] = str(paths.root())
    shell = environ.get("SHELL", "/bin/sh")
    execvp(shell, [shell])
    return EXIT_OK


def cmd_credentials(args: Namespace) -> int:
    from messy_streets import credentials
    action = "set" if args.set else ("clear" if args.clear else "show")
    return credentials.run(action=action, providers=args.set or None,
                           as_json=args.json, verbose=args.verbose)


def cmd_geocode(args: Namespace) -> int:
    from messy_streets import credentials, geocode

    # The file supplies only what the environment has not already set.
    supplied = credentials.load_into_environment()
    if supplied and not args.json:
        print(f"  {len(supplied)} credential(s) read from {credentials.path()}")

    return geocode.run(providers=args.provider, runs=args.runs,
                       observations=args.observations, opt_in=args.i_supply_my_own_keys,
                       as_json=args.json, verbose=args.verbose)


def cmd_unimplemented(args: Namespace) -> int:
    verb = verbs.load()[args.verb]
    message = (f"'{verb.name}' is not built yet — it lands in slice {verb.slice}.\n"
               f"  {verb.description}\n"
               f"Built so far: slice {verbs.IMPLEMENTED_THROUGH}.")
    if args.json:
        print(dumps({"verb": verb.name, "implemented": False,
                     "slice": verb.slice, "message": message}, indent=2))
    else:
        print(message)
    return EXIT_UNAVAILABLE


HANDLERS = {}


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="messy-streets",
        description="Reproduce the MESSY STREETS geocoding benchmark results.",
        epilog=_epilog(),
        formatter_class=RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="verb", metavar="<command>")

    for verb in verbs.load().values():
        sub = subparsers.add_parser(verb.name, help=verb.description, description=verb.description)
        sub.add_argument("--json", action="store_true", help="machine-readable output")
        sub.add_argument("--out", type=str, default=None,
                         help="directory to write into (default: ./out)")
        sub.add_argument("--verbose", action="store_true",
                         help="show the pipeline's own logging")
        if verb.name == "credentials":
            sub.add_argument("--set", action="append", default=None, metavar="PROVIDER",
                             help="prompt for this provider's key (repeatable); "
                                  "omit the value to prompt for all")
            sub.add_argument("--clear", action="store_true",
                             help="delete the credentials file")
        if verb.name in ("credentials", "geocode"):
            sub.add_argument("--credentials", type=str, default=None, metavar="PATH",
                             help="use this credentials file instead of the default")
        if verb.name == "geocode":
            sub.add_argument("--provider", action="append", default=None,
                             help="restrict to this provider (repeatable)")
            sub.add_argument("--runs", type=int, default=10)
            sub.add_argument("--observations", type=int, default=100)
            sub.add_argument("--i-supply-my-own-keys", action="store_true",
                             dest="i_supply_my_own_keys",
                             help="required to query anything; nothing runs without it")
        if verb.name == "pipeline":
            sub.add_argument("action", nargs="?", default="list", choices=["list", "show"])
            sub.add_argument("stage", nargs="?", type=int, default=None)
        if verb.name == "sample":
            sub.add_argument("--limit", type=int, default=None,
                             help="only regenerate this many slices")
        if verb.name == "inspect":
            sub.add_argument("--tier", default="gold", choices=["gold", "silver", "raw"])
            sub.add_argument("-n", type=int, default=5, help="how many records to show")
            sub.add_argument("--contains", default=None, help="only addresses containing this text")
            sub.add_argument("--missing", default=None,
                             help="only records missing this component (e.g. country)")
        sub.set_defaults(handler=HANDLERS.get(verb.name, cmd_unimplemented))

    return parser


HANDLERS.update({
    "doctor": cmd_doctor,
    "smoke": cmd_smoke,
    "tables": cmd_tables,
    "stats": cmd_stats,
    "inspect": cmd_inspect,
    "sample": cmd_sample,
    "pipeline": cmd_pipeline,
    "geocode": cmd_geocode,
    "shell": cmd_shell,
    "credentials": cmd_credentials,
})


def main(argv: List[str] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.verb:
        parser.print_help()
        return EXIT_OK
    if args.out:
        from os import environ
        environ["MS_OUT"] = args.out
    if getattr(args, "credentials", None):
        from os import environ
        environ["MS_CREDENTIALS"] = args.credentials
    return args.handler(args)
