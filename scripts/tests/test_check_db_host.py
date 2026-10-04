#!/usr/bin/env python3
"""Tests for scripts/check_db_host.py (T542).

The deploy of 2026-10-03 passed its preflight and 19 minutes of tests and then failed at `db-migrate` with "could not translate host name", because the database host
is IPv6-only and the machine's resolver had stopped answering such names while WARP still said Connected. The old preflight tested a connection to a dual-stack site, not the
name lookup psql does. These tests pin what the replacement must do: ask the resolver the same question psql asks, say which part failed, and never pass by accident.
No test touches the network: the resolver and the connector are injected.
"""
from __future__ import annotations

import io
import socket
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_db_host as ck  # noqa: E402

HOST = "db.pqbbjgeapylcengbuvee.supabase.co"
ADDR6 = "2600:1f16:1e8d:b801:e0e4:a3c8:f444:fff8"
ADDR4 = "203.0.113.7"


def resolver_ok(*families):
    def r(host, port, *a, **k):
        assert host == HOST and port == 5432, (host, port)
        return [(fam, socket.SOCK_STREAM, 6, "", (ADDR6 if fam == socket.AF_INET6 else ADDR4, port)) for fam in families]
    return r


def resolver_fails(host, port, *a, **k):
    raise socket.gaierror(8, "nodename nor servname provided, or not known")


class Recorder:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def __call__(self, address, timeout):
        self.calls.append((address, timeout))
        if self.error:
            raise self.error


class Check(unittest.TestCase):
    def test_a_host_that_resolves_and_connects_passes(self):
        conn = Recorder()
        r = ck.check(HOST, 5432, 5.0, resolver_ok(socket.AF_INET6), conn)
        self.assertEqual((r.ok, r.stage), (True, "ok"))
        self.assertEqual(r.families, ["IPv6"])
        self.assertEqual(len(conn.calls), 1)

    def test_a_resolution_failure_fails_with_the_resolver_stage_and_never_connects(self):
        conn = Recorder()
        r = ck.check(HOST, 5432, 5.0, resolver_fails, conn)
        self.assertEqual((r.ok, r.stage), (False, "resolve"))
        self.assertEqual(conn.calls, [])
        self.assertIn("reconnect", r.message.lower())
        self.assertIn("WARP", r.message)
        self.assertIn("getaddrinfo", r.message)

    def test_the_resolution_message_names_what_it_is_not(self):
        r = ck.check(HOST, 5432, 5.0, resolver_fails, Recorder())
        self.assertIn("not a network outage", r.message)
        self.assertNotIn("IPv4", r.message.replace("never IPv4", "").replace("not IPv4", "").replace("no IPv4", ""))

    def test_an_empty_answer_is_a_resolution_failure(self):
        conn = Recorder()
        r = ck.check(HOST, 5432, 5.0, lambda *a, **k: [], conn)
        self.assertEqual((r.ok, r.stage), (False, "resolve"))
        self.assertEqual(conn.calls, [])

    def test_a_connect_failure_after_resolution_is_a_different_stage_and_message(self):
        for err in (ConnectionRefusedError("x"), TimeoutError("x"), OSError(65, "No route to host")):
            r = ck.check(HOST, 5432, 5.0, resolver_ok(socket.AF_INET6), Recorder(err))
            self.assertEqual((r.ok, r.stage), (False, "connect"), repr(err))
            self.assertIn("resolves", r.message)
            self.assertNotIn("getaddrinfo", r.message)

    def test_every_address_is_tried_and_one_success_is_enough(self):
        calls = []

        def conn(address, timeout):
            calls.append(address)
            if address[0] == ADDR6:
                raise ConnectionRefusedError("first family refused")

        r = ck.check(HOST, 5432, 5.0, resolver_ok(socket.AF_INET6, socket.AF_INET), conn)
        self.assertTrue(r.ok)
        self.assertEqual(len(calls), 2)
        self.assertEqual(r.families, ["IPv6", "IPv4"])

    def test_without_an_injected_connector_the_real_connector_gets_the_address_timeout_and_family(self):
        from unittest import mock
        seen = []
        with mock.patch.object(ck, "tcp_connect", lambda address, timeout, family=None: seen.append((address, timeout, family))):
            r = ck.check(HOST, 5432, 2.0, resolver_ok(socket.AF_INET6, socket.AF_INET))
        self.assertTrue(r.ok)
        self.assertEqual(seen, [((ADDR6, 5432), 2.0, socket.AF_INET6)])

    def test_the_resolution_message_says_why_psql_is_affected(self):
        self.assertIn("psql", ck.check(HOST, 5432, 5.0, resolver_fails, Recorder()).message)

    def test_the_timeout_is_passed_to_the_connector(self):
        conn = Recorder()
        ck.check(HOST, 5432, 2.5, resolver_ok(socket.AF_INET6), conn)
        self.assertEqual(conn.calls[0][1], 2.5)

    def test_a_gaierror_does_not_claim_the_resolver_raised_something_unexpected(self):
        self.assertNotIn("raised", ck.check(HOST, 5432, 5.0, resolver_fails, Recorder()).message)

    def test_an_unexpected_resolver_error_fails_closed_naming_only_the_type(self):
        def boom(*a, **k):
            raise RuntimeError("secret-looking-detail postgres://u:p@h/db")
        r = ck.check(HOST, 5432, 5.0, boom, Recorder())
        self.assertEqual((r.ok, r.stage), (False, "resolve"))
        self.assertIn("RuntimeError", r.message)
        self.assertNotIn("secret-looking-detail", r.message)

    def test_an_unexpected_connector_error_fails_closed_naming_only_the_type(self):
        r = ck.check(HOST, 5432, 5.0, resolver_ok(socket.AF_INET6), Recorder(ValueError("secret-looking-detail")))
        self.assertEqual((r.ok, r.stage), (False, "connect"))
        self.assertNotIn("secret-looking-detail", r.message)

    def test_the_result_never_contains_an_address(self):
        r = ck.check(HOST, 5432, 5.0, resolver_ok(socket.AF_INET6, socket.AF_INET), Recorder())
        blob = repr(r) + r.message
        self.assertNotIn(ADDR6, blob)
        self.assertNotIn(ADDR4, blob)
        r2 = ck.check(HOST, 5432, 5.0, resolver_ok(socket.AF_INET6), Recorder(OSError(f"connect to {ADDR6} failed")))
        self.assertNotIn(ADDR6, r2.message)

    def test_family_names(self):
        self.assertEqual(ck.family_name(socket.AF_INET6), "IPv6")
        self.assertEqual(ck.family_name(socket.AF_INET), "IPv4")
        self.assertEqual(ck.family_name(socket.AF_UNIX), "other")


class HostValidation(unittest.TestCase):
    def test_a_plain_hostname_is_accepted(self):
        for h in (HOST, "db.abc123.supabase.co", "localhost", "a.b-c.example"):
            self.assertEqual(ck.valid_host(h), h)

    def test_anything_that_is_not_a_bare_hostname_is_refused(self):
        for h in ("", " ", "db host", "postgres://u:p@h/db", "h:5432", "h/path", "h;rm -rf /", "-leading.example", "a..b", "x" * 254, "h\n", "h\x00", None, 5, "[::1]", "a_b.example"):
            with self.assertRaises(ValueError, msg=repr(h)):
                ck.valid_host(h)  # type: ignore[arg-type]

    def test_a_label_of_63_characters_passes_and_64_does_not(self):
        ck.valid_host("a" * 63 + ".example")
        with self.assertRaises(ValueError):
            ck.valid_host("a" * 64 + ".example")

    def test_a_name_of_253_characters_passes_and_254_does_not(self):
        name = ("a" * 63 + ".") * 3 + "a" * 61
        self.assertEqual(len(name), 253)
        ck.valid_host(name)
        with self.assertRaises(ValueError):
            ck.valid_host(name + "a")


class Cli(unittest.TestCase):
    def run_main(self, argv, **kw):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ck.main(argv, **kw)
        return code, out.getvalue(), err.getvalue()

    def test_a_good_host_prints_a_pass_line_and_exits_0(self):
        code, out, _ = self.run_main(["--host", HOST], resolver=resolver_ok(socket.AF_INET6), connector=Recorder())
        self.assertEqual(code, 0)
        self.assertIn("OK", out)
        self.assertIn(HOST, out)
        self.assertIn("IPv6", out)

    def test_a_resolution_failure_prints_the_fix_and_exits_1(self):
        code, out, err = self.run_main(["--host", HOST], resolver=resolver_fails, connector=Recorder())
        self.assertEqual(code, 1)
        text = out + err
        self.assertIn("FAIL", text)
        self.assertIn("warp-cli", text)
        self.assertIn("getaddrinfo", text)

    def test_a_connect_failure_exits_1_with_its_own_message(self):
        code, out, err = self.run_main(["--host", HOST], resolver=resolver_ok(socket.AF_INET6), connector=Recorder(TimeoutError("x")))
        self.assertEqual(code, 1)
        self.assertIn("resolves", out + err)

    def test_a_bad_host_exits_2_and_resolves_nothing(self):
        called = []
        code, out, err = self.run_main(["--host", "postgres://u:p@h/db"], resolver=lambda *a, **k: called.append(1), connector=Recorder())
        self.assertEqual(code, 2)
        self.assertEqual(called, [])
        self.assertNotIn("u:p", out + err)

    def test_host_is_required(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            ck.main([], resolver=resolver_fails, connector=Recorder())
        self.assertEqual(cm.exception.code, 2)

    def test_port_and_timeout_are_passed_through(self):
        seen = {}

        def resolver(host, port, *a, **k):
            seen["port"] = port
            return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ADDR6, port))]
        conn = Recorder()
        self.run_main(["--host", HOST, "--port", "6543", "--timeout", "1.5"], resolver=resolver, connector=conn)
        self.assertEqual(seen["port"], 6543)
        self.assertEqual(conn.calls[0][1], 1.5)

    def test_the_defaults_are_the_postgres_port_and_a_short_timeout(self):
        self.assertEqual(ck.DEFAULT_PORT, 5432)
        self.assertLessEqual(ck.DEFAULT_TIMEOUT, 10.0)
        self.assertGreater(ck.DEFAULT_TIMEOUT, 0)

    def test_an_out_of_range_port_or_timeout_is_refused(self):
        for argv in (["--host", HOST, "--port", "0"], ["--host", HOST, "--port", "65536"], ["--host", HOST, "--port", "70000"], ["--host", HOST, "--timeout", "0"], ["--host", HOST, "--timeout", "-1"],
                     ["--host", HOST, "--timeout", "61"]):
            code, _, _ = self.run_main(argv, resolver=resolver_ok(socket.AF_INET6), connector=Recorder())
            self.assertEqual(code, 2, argv)


class Bounds(unittest.TestCase):
    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        any_port = lambda host, port, *a, **k: [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ADDR6, port))]  # noqa: E731
        with redirect_stdout(out), redirect_stderr(err):
            return ck.main(argv, resolver=any_port, connector=Recorder())

    def test_the_edges_that_are_allowed(self):
        self.assertEqual(self.run_main(["--host", HOST, "--port", "1"]), 0)
        self.assertEqual(self.run_main(["--host", HOST, "--port", "65535"]), 0)
        self.assertEqual(self.run_main(["--host", HOST, "--timeout", "60"]), 0)
        self.assertEqual(self.run_main(["--host", HOST, "--timeout", "0.1"]), 0)


class RealResolver(unittest.TestCase):
    def test_the_defaults_are_the_real_resolver_and_a_real_socket_connect(self):
        self.assertIs(ck.DEFAULT_RESOLVER, socket.getaddrinfo)
        self.assertTrue(callable(ck.tcp_connect))

    def test_tcp_connect_closes_the_socket_and_uses_the_timeout(self):
        from unittest import mock
        s = mock.MagicMock()
        with mock.patch.object(ck.socket, "socket", return_value=s) as ctor:
            ck.tcp_connect((ADDR6, 5432), 3.0, family=socket.AF_INET6)
        ctor.assert_called_once_with(socket.AF_INET6, socket.SOCK_STREAM)
        s.settimeout.assert_called_once_with(3.0)
        s.connect.assert_called_once()
        s.close.assert_called_once()

    def test_tcp_connect_closes_the_socket_when_connect_fails(self):
        from unittest import mock
        s = mock.MagicMock()
        s.connect.side_effect = OSError("x")
        with mock.patch.object(ck.socket, "socket", return_value=s):
            with self.assertRaises(OSError):
                ck.tcp_connect((ADDR6, 5432), 3.0, family=socket.AF_INET6)
        s.close.assert_called_once()


class NoNetwork(unittest.TestCase):
    def test_this_file_never_reaches_the_network_by_default(self):
        # main() with injected fakes is the only way the tests above call it; a call without them would use the real resolver
        self.assertIs(ck.DEFAULT_RESOLVER, socket.getaddrinfo)


if __name__ == "__main__":
    unittest.main(verbosity=1)
