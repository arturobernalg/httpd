import pytest

from pyhttpd.conf import HttpdConf


def _conf(env, trace):
    conf = HttpdConf(env)
    conf.add(f"TraceEnable {trace}")
    conf.start_vhost(domains=[f"test1.{env.http_tld}"], port=env.http_port,
                     doc_root="htdocs/test1", with_ssl=False)
    # the backend does not exist, a denied TRACE is not forwarded
    conf.add("ProxyPass /proxy/ http://127.0.0.1:1/")
    conf.end_vhost()
    conf.install()
    assert env.apache_restart() == 0


def _request(env, method, path):
    options = ['-I'] if method == 'HEAD' else ['-X', method]
    r = env.curl_get(env.mkurl("http", "test1", path), options=options)
    assert r.response, f"no response: {r.stderr}"
    # TRACE is denied on purpose
    env.httpd_error_log.ignore_recent(lognos=["AH01139"])
    allow = r.response["header"].get("allow")
    methods = None if allow is None else \
        {m.strip() for m in allow.split(',') if m.strip()}
    return r.response["status"], methods


class TestTraceDisabledAllow:

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        _conf(env, "off")

    # the 405 of a TRACE denied by TraceEnable lists methods that do work
    @pytest.mark.parametrize("path", ["/index.html", "/no-such-file", "/proxy/x"])
    def test_core_010_001(self, env, path):
        status, allow = _request(env, "TRACE", path)
        assert status == 405
        assert allow is not None, "no Allow field"
        assert {"GET", "HEAD", "OPTIONS"} <= allow, f"Allow: {allow}"
        assert "TRACE" not in allow, f"Allow: {allow}"

    # the advertised methods are really supported
    @pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
    def test_core_010_002(self, env, method):
        assert _request(env, method, "/index.html")[0] == 200

    # OPTIONS does not offer TRACE either
    def test_core_010_003(self, env):
        status, allow = _request(env, "OPTIONS", "/index.html")
        assert status == 200
        assert "TRACE" not in allow


class TestTraceEnabledAllow:

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        _conf(env, "on")

    # unchanged: TRACE works and is offered
    def test_core_010_101(self, env):
        assert _request(env, "TRACE", "/index.html")[0] == 200
        status, allow = _request(env, "OPTIONS", "/index.html")
        assert status == 200
        assert "TRACE" in allow
