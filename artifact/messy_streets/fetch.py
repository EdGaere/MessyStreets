"""Downloading with the retry policy the paper's own downloader used.

The mirror throttles concurrent requests, which is why the construction
pipeline did not use plain wget but `phd/datasets/address/schema_org/v2/wget.py`
— a small wrapper with exponential backoff. A re-scrape that hammered the same
server without it would be both rude and unreliable.

That script is built on `requests`, which this package cannot import: the CLI is
deliberately stdlib-only so `doctor` can diagnose a broken dependency install.
So the *policy* is carried here rather than the file — the same constants, the
same status codes, the same backoff — on top of urllib.

    200        the body, streamed
    403, 404   no such part; this is how the original walk found the end of a
               class, so it is a result rather than an error
    429        throttled: wait base_delay * 2**attempt and try again
    anything   reported as an error, without retrying

The one deliberate divergence is documented in `Outcome.missing`: the original
script's docstring says it retries on 403, but its code returns immediately, and
the part walk depends on that. Retrying 403 would never terminate.
"""

from typing import NamedTuple, Optional

# The originals, from wget.py's download().
MAX_RETRIES = 10
BASE_DELAY = 5.0

MISSING_STATUS = (403, 404)
THROTTLED_STATUS = 429


class Outcome(NamedTuple):
    """What happened. Exactly one of `stream`, `missing` or `error` is meaningful."""
    stream: Optional[object] = None
    missing: bool = False
    error: str = ""
    attempts: int = 1

    @property
    def ok(self) -> bool:
        return self.stream is not None


def open_with_retry(url: str, timeout: float, max_retries: int = MAX_RETRIES,
                    base_delay: float = BASE_DELAY, opener=None,
                    sleep=None, announce=None) -> Outcome:
    """Open `url`, backing off while the mirror says it is being asked too much.

    Returns the live response so the caller can stream it; a part is a few
    hundred megabytes and does not want to be held in memory.
    """
    from time import sleep as real_sleep
    from urllib.error import HTTPError, URLError
    from urllib.request import urlopen

    sleep = sleep or real_sleep
    open_url = opener or urlopen

    for attempt in range(max_retries):
        try:
            return Outcome(stream=open_url(url, timeout=timeout), attempts=attempt + 1)
        except HTTPError as error:
            if error.code in MISSING_STATUS:
                return Outcome(missing=True, attempts=attempt + 1)
            if error.code == THROTTLED_STATUS:
                delay = base_delay * (2 ** attempt)
                if announce:
                    announce(f"throttled ({error.code}), attempt {attempt + 1}"
                             f"/{max_retries}, waiting {delay:.0f}s")
                sleep(delay)
                continue
            return Outcome(error=f"HTTP {error.code}", attempts=attempt + 1)
        except URLError as error:
            return Outcome(error=f"{type(error.reason).__name__}: {error.reason}",
                           attempts=attempt + 1)
        except Exception as error:                                   # noqa: BLE001
            return Outcome(error=f"{type(error).__name__}: {error}",
                           attempts=attempt + 1)

    return Outcome(error=f"max retries exceeded after {max_retries} attempts",
                   attempts=max_retries)
