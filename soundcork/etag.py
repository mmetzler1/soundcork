"""Etag dependencies for the marge API."""

from inspect import iscoroutinefunction

from fastapi import Request, Response
from fastapi_etag import Etag


class WriteEtag(Etag):
    """Sends an etag back on a write, but never rejects one.

    `Etag` answers a request carrying a stale `If-Match` with a 412. That is
    the right thing for a client that can be told about a change, but a
    SoundTouch speaker cannot: Bose pushed account updates from the cloud, and
    soundcork has no such channel. As soon as anything else writes to the
    account -- the dashboard saving a station, for instance -- a speaker holds
    an etag it can never refresh, and a long press on a station button would
    be turned down from then on. The speaker's write wins instead.
    """

    async def __call__(self, request: Request, response: Response) -> str | None:
        generated = self.etag_gen(request)
        if iscoroutinefunction(self.etag_gen):
            generated = await generated  # type: ignore[misc]
        etag = str(generated) if generated else ""
        if etag and self.weak:
            etag = f'W/"{etag}"'
        headers = {"etag": etag} if etag else {}
        if self.extra_headers:
            headers.update(self.extra_headers)
        response.headers.update(headers)
        return etag
