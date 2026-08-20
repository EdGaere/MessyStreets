"""credentials — where the geocoder API keys live, and how they get in.

They live in exactly one place: a file on the host, outside the repository, at
mode 0600. Not in the image, which every user of the artefact pulls; not in the
repository, which is one `git add -A` away from being public — the failure this
artefact exists partly to have corrected.

The container borrows the file for the length of one command. It is mounted
read-only, read into the process environment by the CLI, and goes away with the
container. A read-only mount rather than --env-file, because --env-file puts the
values into the container's configuration where `docker inspect` shows them to
anyone with Docker access while a run is in progress; on a shared machine that
is a real difference.

Environment variables win over the file, so continuous integration and one-off
overrides need no edit.

This verb runs on the host, like the preflight half of `doctor`, and for the
same reason: the file has to be written where the container cannot reach.
"""

from getpass import getpass
from json import dumps
from os import chmod, environ
from pathlib import Path
from typing import Dict, List, Optional

# Provider -> credential, for the nine that need one. Nominatim, Photon and
# ArcGIS are absent because they need no key.
from messy_streets.geocode import PROVIDERS

DEFAULT_PATH = Path(
    environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "messy-streets" / "credentials.hjson"


def path() -> Path:
    """The credentials file in force: --credentials, then MS_CREDENTIALS, then the default."""
    override = environ.get("MS_CREDENTIALS")
    return Path(override).expanduser() if override else DEFAULT_PATH


def needed() -> Dict[str, str]:
    """Credential name -> provider, for the providers that require one."""
    return {credential: name for name, (_, credential, _) in PROVIDERS.items() if credential}


def read(source: Optional[Path] = None) -> Dict[str, str]:
    """Load the file. Missing file is not an error — it means nothing is set."""
    import hjson

    target = source or path()
    if not target.is_file():
        return {}
    with target.open(encoding="utf8") as handle:
        document = hjson.load(handle)
    section = document.get("geocoders", document)
    return {key: value for key, value in section.items()
            if value not in (None, "", "null")}


def write(values: Dict[str, str], target: Optional[Path] = None) -> Path:
    """Write the file at 0600, creating its directory if needed."""
    destination = target or path()
    destination.parent.mkdir(parents=True, exist_ok=True)

    lines = ["/*", "  MESSY STREETS — geocoder credentials.", "",
             "  Written by `messy-streets credentials`. Mode 0600, outside any git tree.",
             "  A null value means that provider is not queried.", "*/", "{", "  geocoders:", "  {"]
    for credential in sorted(needed()):
        value = values.get(credential)
        lines.append(f"    {credential}: " + (dumps(value) if value else "null"))
    lines += ["  }", "}"]

    destination.write_text("\n".join(lines) + "\n", encoding="utf8")
    chmod(destination, 0o600)
    return destination


def load_into_environment(source: Optional[Path] = None) -> List[str]:
    """Put the file's values into os.environ without overriding what is already set.

    Called before any provider is constructed. Returns the names it supplied,
    never the values.
    """
    supplied = []
    for credential, value in read(source).items():
        if not environ.get(credential):
            environ[credential] = str(value)
            supplied.append(credential)
    return supplied


def status() -> List[dict]:
    stored = read()
    rows = []
    for credential, provider in sorted(needed().items()):
        from_environment = bool(environ.get(credential))
        rows.append({
            "provider": provider,
            "credential": credential,
            "set": from_environment or credential in stored,
            "source": "environment" if from_environment else ("file" if credential in stored else None),
        })
    return rows


def run(action: str = "show", providers: Optional[List[str]] = None,
        as_json: bool = False, verbose: bool = False) -> int:
    from messy_streets.cli import EXIT_ENVIRONMENT, EXIT_OK, EXIT_UNAVAILABLE

    target = path()

    if action == "clear":
        existed = target.is_file()
        if existed:
            target.unlink()
        if as_json:
            print(dumps({"path": str(target), "removed": existed,
                         "exit_code": EXIT_OK}, indent=2))
        else:
            print(f"removed {target}" if existed else f"nothing to remove at {target}")
        return EXIT_OK

    if action == "set":
        by_provider = {provider: credential for credential, provider in needed().items()}
        chosen = providers or sorted(by_provider)
        unknown = [p for p in chosen if p not in by_provider]
        if unknown:
            print(f"unknown or keyless provider(s): {', '.join(unknown)}")
            print(f"providers needing a key: {', '.join(sorted(by_provider))}")
            return EXIT_UNAVAILABLE

        values = read()
        print(f"\nWriting to {target}")
        print("Values are not echoed. Press Enter to leave one unset and skip that provider.\n")
        for provider in chosen:
            credential = by_provider[provider]
            state = "set" if credential in values else "not set"
            entered = getpass(f"  {provider:<18} {credential} [{state}]: ").strip()
            if entered:
                values[credential] = entered
        written = write(values, target)
        print(f"\nwrote {written} (mode 0600)")
        print(f"{len(values)} of {len(needed())} credentials set.")
        return EXIT_OK

    rows = status()
    if as_json:
        print(dumps({"path": str(target), "exists": target.is_file(),
                     "credentials": rows,
                     "set": sum(1 for r in rows if r["set"]),
                     "exit_code": EXIT_OK}, indent=2))
        return EXIT_OK

    print(f"\nCredentials file: {target}"
          f"{'' if target.is_file() else '  (does not exist yet)'}\n")
    print(f"  {'provider':<18}{'credential':<26}{'status':<12}source")
    print("  " + "-" * 68)
    for row in rows:
        print(f"  {row['provider']:<18}{row['credential']:<26}"
              f"{'set' if row['set'] else 'not set':<12}{row['source'] or ''}")

    unset = [r for r in rows if not r["set"]]
    print(f"\n  {len(rows) - len(unset)} of {len(rows)} set. Nominatim, Photon and ArcGIS "
          "need no key and always work.")
    if unset:
        print(f"\n  messy-streets credentials --set {unset[0]['provider']}"
              "        to add one, without echoing it")
    print("  Environment variables take precedence over the file.")
    return EXIT_OK
