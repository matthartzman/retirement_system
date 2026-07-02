from __future__ import annotations

"""Small Flask-compatible facade backed only by Python stdlib.

This module exists to remove the Flask/Werkzeug runtime dependency without a
flag-day rewrite of every route function.  It implements the narrow subset of
Flask semantics used by ``src.server``:

* ``app.route`` decorators and path converters (``<name>``, ``<int:name>``,
  ``<path:name>``)
* request-local ``request`` and ``g`` proxies
* JSON/text/file/redirect responses
* before/after request hooks and app-level error handling
* a minimal ``test_client`` used by pywebview desktop mode and regression tests

It is not intended to be a public web framework.  The application is a
single-user local desktop/server process.
"""

import contextvars
import html
import json
import mimetypes
import os
import re
import traceback
from dataclasses import dataclass, field
from http import HTTPStatus
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit

_CURRENT_REQUEST: contextvars.ContextVar["LocalRequest | None"] = contextvars.ContextVar("retirement_request", default=None)
_CURRENT_G: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("retirement_g", default=None)


class HTTPException(Exception):
    """Tiny stand-in for Werkzeug's HTTPException."""

    code = 500
    description = "HTTP error"

    def __init__(self, description: str | None = None, code: int | None = None) -> None:
        super().__init__(description or self.description)
        if code is not None:
            self.code = int(code)
        self.description = description or self.description


class ProxyFix:
    """No-op compatibility wrapper for the old optional Werkzeug middleware."""

    def __init__(self, app: Any, **_kwargs: Any) -> None:
        self.app = app

    def __call__(self, environ: dict, start_response: Callable) -> Any:  # pragma: no cover - WSGI compatibility
        return self.app(environ, start_response)


class HeaderMap(dict):
    """Case-insensitive-ish header mapping preserving canonical values."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.update(*args, **kwargs)

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(str(key), str(value))

    def get(self, key: str, default: Any = None) -> Any:
        if key in self:
            return super().get(key, default)
        needle = str(key).lower()
        for k, v in self.items():
            if str(k).lower() == needle:
                return v
        return default

    def setdefault(self, key: str, default: Any = None) -> Any:
        found = self.get(key, None)
        if found is not None:
            return found
        self[key] = default
        return default


class QueryArgs(dict):
    """Flask-like query args with ``get(type=...)`` support."""

    def get(self, key: str, default: Any = None, type: Callable | None = None) -> Any:  # noqa: A002 - Flask API name
        value = super().get(key, default)
        if isinstance(value, list):
            value = value[0] if value else default
        if type is not None and value is not None:
            try:
                return type(value)
            except Exception:
                return default
        return value


@dataclass
class LocalRequest:
    method: str
    full_path: str
    headers: HeaderMap = field(default_factory=HeaderMap)
    body: bytes = b""
    remote_addr: str = "127.0.0.1"
    environ: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        parsed = urlsplit(self.full_path)
        self.path = parsed.path or "/"
        self.query_string = parsed.query
        self.args = QueryArgs({k: (v[0] if len(v) == 1 else v) for k, v in parse_qs(parsed.query, keep_blank_values=True).items()})
        self.method = str(self.method or "GET").upper()
        scheme = "https" if str(self.headers.get("X-Forwarded-Proto", "")).lower() == "https" else "http"
        host = self.headers.get("Host", "127.0.0.1")
        self.url = f"{scheme}://{host}{self.path}" + (f"?{self.query_string}" if self.query_string else "")
        self.is_secure = scheme == "https"
        self.cookies = self._parse_cookies()

    def _parse_cookies(self) -> dict[str, str]:
        raw = self.headers.get("Cookie", "")
        if not raw:
            return {}
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
        except Exception:
            return {}
        return {k: morsel.value for k, morsel in cookie.items()}

    def get_json(self, force: bool = False, silent: bool = False) -> Any:
        ctype = str(self.headers.get("Content-Type", "")).lower()
        if not force and self.body and "json" not in ctype and ctype:
            if silent:
                return None
            raise ValueError("Request content type is not JSON")
        if not self.body:
            return None
        try:
            return json.loads(self.body.decode("utf-8"))
        except Exception:
            if silent:
                return None
            raise

    def get_data(self, as_text: bool = False) -> bytes | str:
        if as_text:
            return self.body.decode("utf-8", errors="replace")
        return self.body


class _RequestProxy:
    def _get(self) -> LocalRequest:
        req = _CURRENT_REQUEST.get()
        if req is None:
            # Import-time tests sometimes touch ``request`` outside a request.
            return LocalRequest("GET", "/")
        return req

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get(), name)

    def __bool__(self) -> bool:
        return _CURRENT_REQUEST.get() is not None


class _GProxy:
    def _get(self) -> dict[str, Any]:
        data = _CURRENT_G.get()
        if data is None:
            data = {}
            _CURRENT_G.set(data)
        return data

    def __getattr__(self, name: str) -> Any:
        try:
            return self._get()[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            self._get()[name] = value


request = _RequestProxy()
g = _GProxy()


class Response:
    """Minimal response object with Flask-like helpers."""

    default_mimetype = "text/html; charset=utf-8"

    def __init__(
        self,
        response: Any = b"",
        status: int = 200,
        headers: dict[str, Any] | None = None,
        mimetype: str | None = None,
        content_type: str | None = None,
    ) -> None:
        self.status_code = int(status or 200)
        self.headers = HeaderMap(headers or {})
        self._body_source = response
        ctype = content_type or mimetype
        if ctype:
            if mimetype and ";" not in ctype and (ctype.startswith("text/") or ctype in {"application/json", "text/csv"}):
                ctype = f"{ctype}; charset=utf-8" if ctype.startswith("text/") else ctype
            self.headers.setdefault("Content-Type", ctype)
        self.headers.setdefault("Content-Type", self.default_mimetype)

    @property
    def content_type(self) -> str:
        return str(self.headers.get("Content-Type", ""))

    @property
    def mimetype(self) -> str:
        return self.content_type.split(";", 1)[0]

    def iter_bytes(self) -> Iterable[bytes]:
        src = self._body_source
        if src is None:
            return []
        if isinstance(src, bytes):
            return [src]
        if isinstance(src, str):
            return [src.encode("utf-8")]
        if isinstance(src, bytearray):
            return [bytes(src)]
        if isinstance(src, dict) or isinstance(src, list):
            return [json.dumps(src, ensure_ascii=False).encode("utf-8")]
        try:
            iterator = iter(src)
        except TypeError:
            return [str(src).encode("utf-8")]
        chunks: list[bytes] = []
        for chunk in iterator:
            if isinstance(chunk, bytes):
                chunks.append(chunk)
            else:
                chunks.append(str(chunk).encode("utf-8"))
        return chunks

    def get_data(self, as_text: bool = False) -> bytes | str:
        data = b"".join(self.iter_bytes())
        if as_text:
            return data.decode("utf-8", errors="replace")
        return data

    def get_json(self, silent: bool = False) -> Any:
        try:
            return json.loads(self.get_data(as_text=True))
        except Exception:
            if silent:
                return None
            raise

    def set_cookie(self, key: str, value: str = "", **kwargs: Any) -> None:
        parts = [f"{key}={quote(str(value))}"]
        if kwargs.get("max_age") is not None:
            parts.append(f"Max-Age={int(kwargs['max_age'])}")
        if kwargs.get("path"):
            parts.append(f"Path={kwargs['path']}")
        else:
            parts.append("Path=/")
        if kwargs.get("secure"):
            parts.append("Secure")
        if kwargs.get("httponly"):
            parts.append("HttpOnly")
        if kwargs.get("samesite"):
            parts.append(f"SameSite={kwargs['samesite']}")
        self.headers["Set-Cookie"] = "; ".join(parts)

    def delete_cookie(self, key: str, **_kwargs: Any) -> None:
        self.headers["Set-Cookie"] = f"{key}=; Max-Age=0; Path=/"


class _Rule:
    def __init__(self, rule: str, methods: Iterable[str], endpoint: str) -> None:
        self.rule = rule
        self.methods = frozenset(str(m).upper() for m in methods)
        self.endpoint = endpoint


class _UrlMap:
    def __init__(self, routes: list["_Route"]) -> None:
        self._routes = routes

    def iter_rules(self) -> Iterable[_Rule]:
        for route in self._routes:
            yield _Rule(route.rule, route.methods, route.endpoint)


@dataclass
class _Route:
    rule: str
    methods: set[str]
    func: Callable
    endpoint: str
    regex: re.Pattern[str]
    converters: dict[str, Callable[[str], Any]]


def _compile_rule(rule: str) -> tuple[re.Pattern[str], dict[str, Callable[[str], Any]]]:
    converters: dict[str, Callable[[str], Any]] = {}
    pattern = ""
    pos = 0
    token_re = re.compile(r"<(?:(int|path):)?([A-Za-z_][A-Za-z0-9_]*)>")
    for match in token_re.finditer(rule):
        pattern += re.escape(rule[pos:match.start()])
        converter, name = match.group(1) or "str", match.group(2)
        if converter == "int":
            pattern += rf"(?P<{name}>\d+)"
            converters[name] = int
        elif converter == "path":
            pattern += rf"(?P<{name}>.+)"
            converters[name] = lambda x: unquote(x)
        else:
            pattern += rf"(?P<{name}>[^/]+)"
            converters[name] = lambda x: unquote(x)
        pos = match.end()
    pattern += re.escape(rule[pos:])
    return re.compile(rf"^{pattern}$"), converters


class _Logger:
    def exception(self, message: str, exc_info: Any = None) -> None:  # pragma: no cover - diagnostic path
        print(message)
        if exc_info:
            traceback.print_exception(exc_info if isinstance(exc_info, BaseException) else None)

    def info(self, message: str, *args: Any) -> None:  # pragma: no cover
        print(message % args if args else message)

    def warning(self, message: str, *args: Any) -> None:  # pragma: no cover
        print(message % args if args else message)


class Flask:
    """Route registry and dispatcher with a Flask-compatible surface."""

    response_class = Response

    def __init__(self, import_name: str, static_folder: str | None = None, **_kwargs: Any) -> None:
        self.import_name = import_name
        self.static_folder = static_folder
        self.routes: list[_Route] = []
        self.before_request_funcs: list[Callable] = []
        self.after_request_funcs: list[Callable[[Response], Response]] = []
        self.error_handlers: list[tuple[type[BaseException], Callable]] = []
        self.logger = _Logger()
        self.wsgi_app = self

    @property
    def url_map(self) -> _UrlMap:
        return _UrlMap(self.routes)

    def route(self, rule: str, methods: Iterable[str] | None = None, **_options: Any) -> Callable:
        methods_set = {str(m).upper() for m in (methods or ["GET"])}
        if "GET" in methods_set:
            methods_set.add("HEAD")
        regex, converters = _compile_rule(rule)

        def decorator(func: Callable) -> Callable:
            self.routes.append(_Route(rule=rule, methods=methods_set, func=func, endpoint=func.__name__, regex=regex, converters=converters))
            return func

        return decorator

    def before_request(self, func: Callable) -> Callable:
        self.before_request_funcs.append(func)
        return func

    def after_request(self, func: Callable[[Response], Response]) -> Callable[[Response], Response]:
        self.after_request_funcs.append(func)
        return func

    def errorhandler(self, exc_type: type[BaseException]) -> Callable:
        def decorator(func: Callable) -> Callable:
            self.error_handlers.append((exc_type, func))
            return func

        return decorator

    def test_client(self) -> "TestClient":
        return TestClient(self)

    def run(self, host: str = "127.0.0.1", port: int = 5050, debug: bool = False, **_kwargs: Any) -> None:
        from .server import run_local_server

        run_local_server(self, host=host, port=int(port), debug=debug)

    def dispatch_request(self, req: LocalRequest) -> Response:
        token_req = _CURRENT_REQUEST.set(req)
        token_g = _CURRENT_G.set({})
        try:
            for hook in self.before_request_funcs:
                rv = hook()
                if rv is not None:
                    return self._finalize(rv)
            route, kwargs = self._match(req.path, req.method)
            if route is None:
                return Response(json.dumps({"success": False, "error": "Not found"}), status=404, content_type="application/json")
            return self._finalize(route.func(**kwargs))
        except BaseException as exc:  # noqa: BLE001 - app-level handler parity
            handler = self._error_handler_for(exc)
            if handler:
                try:
                    return self._finalize(handler(exc))
                except BaseException as nested:  # noqa: BLE001
                    return self._exception_response(nested)
            return self._exception_response(exc)
        finally:
            _CURRENT_REQUEST.reset(token_req)
            _CURRENT_G.reset(token_g)

    def _match(self, path: str, method: str) -> tuple[_Route | None, dict[str, Any]]:
        method = str(method or "GET").upper()
        if method == "HEAD":
            method = "GET"
        for route in self.routes:
            if method not in route.methods and not (method == "OPTIONS" and "OPTIONS" in route.methods):
                continue
            match = route.regex.match(path)
            if not match:
                continue
            kwargs = {}
            for key, raw in match.groupdict().items():
                conv = route.converters.get(key, lambda x: x)
                kwargs[key] = conv(raw)
            return route, kwargs
        return None, {}

    def _error_handler_for(self, exc: BaseException) -> Callable | None:
        for exc_type, handler in reversed(self.error_handlers):
            try:
                if isinstance(exc, exc_type):
                    return handler
            except TypeError:
                continue
        return None

    def _exception_response(self, exc: BaseException) -> Response:
        message = f"{exc.__class__.__name__}: {exc}" if str(exc) else exc.__class__.__name__
        return Response(json.dumps({"success": False, "error": message}), status=500, content_type="application/json")

    def _finalize(self, rv: Any) -> Response:
        response = normalize_response(rv)
        for hook in reversed(self.after_request_funcs):
            response = normalize_response(hook(response))
        return response

    def handle_http(self, method: str, target: str, headers: dict[str, Any] | None = None, body: bytes = b"", remote_addr: str = "127.0.0.1") -> Response:
        return self.dispatch_request(LocalRequest(method, target, HeaderMap(headers or {}), body, remote_addr=remote_addr))

    def __call__(self, environ: dict, start_response: Callable) -> Iterable[bytes]:  # pragma: no cover - legacy WSGI bridge
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/") or "/"
        qs = environ.get("QUERY_STRING", "")
        length = int(environ.get("CONTENT_LENGTH") or 0)
        body = environ.get("wsgi.input").read(length) if length and environ.get("wsgi.input") else b""
        headers = {k[5:].replace("_", "-").title(): v for k, v in environ.items() if k.startswith("HTTP_")}
        if environ.get("CONTENT_TYPE"):
            headers["Content-Type"] = environ.get("CONTENT_TYPE")
        resp = self.handle_http(method, path + (f"?{qs}" if qs else ""), headers, body, environ.get("REMOTE_ADDR", "127.0.0.1"))
        status_line = f"{resp.status_code} {HTTPStatus(resp.status_code).phrase if resp.status_code in HTTPStatus._value2member_map_ else ''}".strip()
        start_response(status_line, list(resp.headers.items()))
        return resp.iter_bytes()


def normalize_response(rv: Any) -> Response:
    status = None
    headers = None
    body = rv
    if isinstance(rv, tuple):
        if len(rv) == 3:
            body, status, headers = rv
        elif len(rv) == 2:
            body, status = rv
        elif len(rv) == 1:
            body = rv[0]
    if isinstance(body, Response):
        resp = body
        if status is not None:
            resp.status_code = int(status)
        if headers:
            resp.headers.update(headers)
        return resp
    if isinstance(body, (dict, list)):
        resp = jsonify(body)
    elif body is None:
        resp = Response(b"", status=int(status or 204))
    else:
        resp = Response(body)
    if status is not None:
        resp.status_code = int(status)
    if headers:
        resp.headers.update(headers)
    return resp


def jsonify(*args: Any, **kwargs: Any) -> Response:
    if args and kwargs:
        payload: Any = {"args": args, **kwargs}
    elif len(args) == 1 and not kwargs:
        payload = args[0]
    elif args:
        payload = list(args)
    else:
        payload = kwargs
    data = json.dumps(payload, ensure_ascii=False, sort_keys=False, default=str).encode("utf-8")
    return Response(data, status=200, content_type="application/json")


def make_response(body: Any = b"", status: int = 200, headers: dict[str, Any] | None = None) -> Response:
    return normalize_response((body, status, headers or {}))


def redirect(location: str, code: int = 302) -> Response:
    escaped = html.escape(str(location), quote=True)
    return Response(f'<!doctype html><title>Redirecting</title><a href="{escaped}">Redirecting</a>', status=code, headers={"Location": str(location)}, content_type="text/html; charset=utf-8")


def send_file(path: str | os.PathLike[str], mimetype: str | None = None, as_attachment: bool = False, download_name: str | None = None, **_kwargs: Any) -> Response:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return Response(json.dumps({"success": False, "error": "File not found"}), status=404, content_type="application/json")
    ctype = mimetype or mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    headers: dict[str, str] = {"Content-Type": ctype}
    if as_attachment:
        name = download_name or p.name
        headers["Content-Disposition"] = f'attachment; filename="{name}"'
    return Response(p.read_bytes(), status=200, headers=headers)


def send_from_directory(directory: str | os.PathLike[str], filename: str, **kwargs: Any) -> Response:
    root = Path(directory).resolve()
    target = (root / filename).resolve()
    try:
        target.relative_to(root)
    except Exception:
        return Response(json.dumps({"success": False, "error": "Invalid path"}), status=403, content_type="application/json")
    return send_file(target, **kwargs)


def url_for(endpoint: str, **values: Any) -> str:
    if endpoint == "static":
        filename = values.get("filename", "")
        return "/" + str(filename).lstrip("/")
    query = urlencode({k: v for k, v in values.items() if v is not None})
    return f"/{endpoint}" + (f"?{query}" if query else "")


class TestClient:
    def __init__(self, app: Flask) -> None:
        self.app = app

    def open(self, path: str, method: str = "GET", json: Any = None, data: bytes | str | None = None, content_type: str | None = None, headers: dict[str, Any] | None = None, **_kwargs: Any) -> Response:  # noqa: A002 - Flask API name
        hdrs = HeaderMap(headers or {})
        body = b""
        if json is not None:
            body = __import__("json").dumps(json).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        elif data is not None:
            body = data if isinstance(data, bytes) else str(data).encode("utf-8")
            if content_type:
                hdrs.setdefault("Content-Type", content_type)
        elif content_type:
            hdrs.setdefault("Content-Type", content_type)
        hdrs.setdefault("Host", "127.0.0.1")
        return self.app.handle_http(method, path, hdrs, body)

    def get(self, path: str, **kwargs: Any) -> Response:
        return self.open(path, method="GET", **kwargs)

    def post(self, path: str, **kwargs: Any) -> Response:
        return self.open(path, method="POST", **kwargs)

    def put(self, path: str, **kwargs: Any) -> Response:
        return self.open(path, method="PUT", **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Response:
        return self.open(path, method="DELETE", **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Response:
        return self.open(path, method="PATCH", **kwargs)
