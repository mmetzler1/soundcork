"""Unit tests for the marge etag dependencies."""

import asyncio

import pytest
from fastapi import Request, Response
from fastapi_etag import Etag
from fastapi_etag.dependency import PreconditionFailed

from soundcork.etag import WriteEtag


def make_request(headers: dict[str, str]) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": "PUT", "path": "/", "headers": raw})


def resolve(dependency, request, response):
    """Run a FastAPI dependency the way the framework would."""
    return asyncio.run(dependency(request, response))


def test_write_etag_accepts_a_stale_if_match():
    """A speaker cannot be told its cached etag went stale, so it must not lose."""
    dependency = WriteEtag(etag_gen=lambda _: "current", weak=False)
    response = Response()

    etag = resolve(dependency, make_request({"if-match": "long-outdated"}), response)

    assert etag == "current"
    assert response.headers["etag"] == "current"


def test_plain_etag_would_have_rejected_that_same_request():
    dependency = Etag(etag_gen=lambda _: "current", weak=False)

    with pytest.raises(PreconditionFailed):
        resolve(dependency, make_request({"if-match": "long-outdated"}), Response())


def test_write_etag_passes_extra_headers_through():
    dependency = WriteEtag(
        etag_gen=lambda _: "current",
        weak=False,
        extra_headers={"method_name": "putPreset"},
    )
    response = Response()

    resolve(dependency, make_request({}), response)

    assert response.headers["method_name"] == "putPreset"
