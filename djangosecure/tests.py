import cStringIO as StringIO

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.http import HttpResponse
from django.test import TestCase

from .test_utils import override_settings, RequestFactory



class SecurityMiddlewareTest(TestCase):
    @property
    def middleware(self):
        from djangosecure.middleware import SecurityMiddleware
        return SecurityMiddleware()


    def response(self, *args, **kwargs):
        headers = kwargs.pop("headers", {})
        response = HttpResponse(*args, **kwargs)
        for k, v in headers.iteritems():
            response[k] = v
        return response


    def process_response(self, *args, **kwargs):
        return self.middleware.process_response(
            "request not used", self.response(*args, **kwargs))


    request = RequestFactory()


    def process_request(self, method, *args, **kwargs):
        if kwargs.pop("secure", False):
            kwargs["wsgi.url_scheme"] = "https"
        req = getattr(self.request, method.lower())(*args, **kwargs)
        return self.middleware.process_request(req)


    @override_settings(SECURE_FRAME_DENY=True)
    def test_frame_deny_on(self):
        """
        With SECURE_FRAME_DENY True, the middleware adds "x-frame-options:
        DENY" to the response.

        """
        self.assertEqual(self.process_response()["x-frame-options"], "DENY")


    @override_settings(SECURE_FRAME_DENY=True)
    def test_frame_deny_already_present(self):
        """
        The middleware will not override an "x-frame-options" header already
        present in the response.

        """
        response = self.process_response(headers={"x-frame-options": "ALLOW"})
        self.assertEqual(response["x-frame-options"], "ALLOW")


    @override_settings(SECURE_FRAME_DENY=False)
    def test_frame_deny_off(self):
        """
        With SECURE_FRAME_DENY False, the middleware does not add an
        "x-frame-options" header to the response.

        """
        self.assertFalse("x-frame-options" in self.process_response())


    @override_settings(SECURE_STS_SECONDS=3600)
    def test_sts_on(self):
        """
        With SECURE_STS_SECONDS=3600, the middleware adds
        "strict-transport-security: max-age=3600" to the response.

        """
        self.assertEqual(
            self.process_response()["strict-transport-security"],
            "max-age=3600")


    @override_settings(SECURE_STS_SECONDS=3600)
    def test_sts_already_present(self):
        """
        The middleware will not override a "strict-transport-security" header
        already present in the response.

        """
        response = self.process_response(
            headers={"strict-transport-security": "max-age=7200"})
        self.assertEqual(response["strict-transport-security"], "max-age=7200")


    @override_settings(SECURE_STS_SECONDS=0)
    def test_sts_off(self):
        """
        With SECURE_STS_SECONDS of 0, the middleware does not add an
        "strict-transport-security" header to the response.

        """
        self.assertFalse("strict-transport-security" in self.process_response())


    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_ssl_redirect_on(self):
        """
        With SECURE_SSL_REDIRECT True, the middleware redirects any non-secure
        requests to the https:// version of the same URL.

        """
        ret = self.process_request("get", "/some/url")
        self.assertEqual(ret.status_code, 301)
        self.assertEqual(ret["Location"], "https://testserver/some/url")


    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_no_redirect_ssl(self):
        """
        The middleware does not redirect secure requests.

        """
        ret = self.process_request("get", "/some/url", secure=True)
        self.assertEqual(ret, None)


    @override_settings(SECURE_SSL_REDIRECT=False)
    def test_ssl_redirect_off(self):
        """
        With SECURE_SSL_REDIRECT False, the middleware does no redirect.

        """
        ret = self.process_request("get", "/some/url")
        self.assertEqual(ret, None)



def fake_test():
    return set(["SOME_WARNING"])

fake_test.messages = {
    "SOME_WARNING": "This is the warning message."
    }

def nomsg_test():
    return set(["OTHER WARNING"])



class CheckSettingsCommandTest(TestCase):
    def call(self, **options):
        stdout = options.setdefault("stdout", StringIO.StringIO())
        stderr = options.setdefault("stderr", StringIO.StringIO())

        call_command("checksecure", **options)

        stderr.seek(0)
        stdout.seek(0)

        return stdout.read(), stderr.read()


    @override_settings(SECURE_CHECKS=["djangosecure.tests.fake_test"])
    def test_prints_messages(self):
        stdout, stderr = self.call()
        self.assertTrue("This is the warning message." in stderr)


    @override_settings(SECURE_CHECKS=["djangosecure.tests.nomsg_test"])
    def test_prints_code_if_no_message(self):
        stdout, stderr = self.call()
        self.assertTrue("OTHER WARNING" in stderr)


    @override_settings(SECURE_CHECKS=["djangosecure.tests.fake_test"])
    def test_prints_check_names(self):
        stdout, stderr = self.call()
        self.assertTrue("djangosecure.tests.fake_test" in stdout)


    @override_settings(SECURE_CHECKS=["djangosecure.tests.fake_test"])
    def test_no_verbosity(self):
        stdout, stderr = self.call(verbosity=0)
        self.assertEqual(stdout, "")


    @override_settings(SECURE_CHECKS=[])
    def test_all_clear(self):
        stdout, stderr = self.call()
        self.assertTrue("All clear!" in stdout)



class CheckSessionCookieSecureTest(TestCase):
    @property
    def func(self):
        from djangosecure.check.sessions import check_session_cookie_secure
        return check_session_cookie_secure


    @override_settings(
        SESSION_COOKIE_SECURE=False,
        INSTALLED_APPS=["django.contrib.sessions"],
        MIDDLEWARE_CLASSES=[])
    def test_session_cookie_secure_with_installed_app(self):
        """
        Warns if SESSION_COOKIE_SECURE is off and "django.contrib.sessions" is
        in INSTALLED_APPS.

        """
        self.assertEqual(
            self.func(), set(["SESSION_COOKIE_NOT_SECURE_APP_INSTALLED"]))


    @override_settings(
        SESSION_COOKIE_SECURE=False,
        INSTALLED_APPS=[],
        MIDDLEWARE_CLASSES=[
            "django.contrib.sessions.middleware.SessionMiddleware"])
    def test_session_cookie_secure_with_middleware(self):
        """
        Warns if SESSION_COOKIE_SECURE is off and
        "django.contrib.sessions.middleware.SessionMiddleware" is in
        MIDDLEWARE_CLASSES.

        """
        self.assertEqual(
            self.func(), set(["SESSION_COOKIE_NOT_SECURE_MIDDLEWARE"]))


    @override_settings(
        SESSION_COOKIE_SECURE=False,
        INSTALLED_APPS=["django.contrib.sessions"],
        MIDDLEWARE_CLASSES=[
            "django.contrib.sessions.middleware.SessionMiddleware"])
    def test_session_cookie_secure_both(self):
        """
        If SESSION_COOKIE_SECURE is off and we find both the session app and
        the middleware, we just provide one common warning.

        """
        self.assertEqual(
            self.func(), set(["SESSION_COOKIE_NOT_SECURE"]))


    @override_settings(
        SESSION_COOKIE_SECURE=True,
        INSTALLED_APPS=["django.contrib.sessions"],
        MIDDLEWARE_CLASSES=[
            "django.contrib.sessions.middleware.SessionMiddleware"])
    def test_session_cookie_secure_true(self):
        """
        If SESSION_COOKIE_SECURE is on, there's no warning about it.

        """
        self.assertEqual(self.func(), set())



class CheckSessionCookieHttpOnlyTest(TestCase):
    @property
    def func(self):
        from djangosecure.check.sessions import check_session_cookie_httponly
        return check_session_cookie_httponly


    @override_settings(
        SESSION_COOKIE_HTTPONLY=False,
        INSTALLED_APPS=["django.contrib.sessions"],
        MIDDLEWARE_CLASSES=[])
    def test_session_cookie_httponly_with_installed_app(self):
        """
        Warns if SESSION_COOKIE_HTTPONLY is off and "django.contrib.sessions"
        is in INSTALLED_APPS.

        """
        self.assertEqual(
            self.func(), set(["SESSION_COOKIE_NOT_HTTPONLY_APP_INSTALLED"]))


    @override_settings(
        SESSION_COOKIE_HTTPONLY=False,
        INSTALLED_APPS=[],
        MIDDLEWARE_CLASSES=[
            "django.contrib.sessions.middleware.SessionMiddleware"])
    def test_session_cookie_httponly_with_middleware(self):
        """
        Warns if SESSION_COOKIE_HTTPONLY is off and
        "django.contrib.sessions.middleware.SessionMiddleware" is in
        MIDDLEWARE_CLASSES.

        """
        self.assertEqual(
            self.func(), set(["SESSION_COOKIE_NOT_HTTPONLY_MIDDLEWARE"]))


    @override_settings(
        SESSION_COOKIE_HTTPONLY=False,
        INSTALLED_APPS=["django.contrib.sessions"],
        MIDDLEWARE_CLASSES=[
            "django.contrib.sessions.middleware.SessionMiddleware"])
    def test_session_cookie_httponly_both(self):
        """
        If SESSION_COOKIE_HTTPONLY is off and we find both the session app and
        the middleware, we just provide one common warning.

        """
        self.assertTrue(
            self.func(), set(["SESSION_COOKIE_NOT_HTTPONLY"]))


    @override_settings(
        SESSION_COOKIE_HTTPONLY=True,
        INSTALLED_APPS=["django.contrib.sessions"],
        MIDDLEWARE_CLASSES=[
            "django.contrib.sessions.middleware.SessionMiddleware"])
    def test_session_cookie_httponly_true(self):
        """
        If SESSION_COOKIE_HTTPONLY is on, there's no warning about it.

        """
        self.assertEqual(self.func(), set())



class CheckSecurityMiddlewareTest(TestCase):
    @property
    def func(self):
        from djangosecure.check.djangosecure import check_security_middleware
        return check_security_middleware


    @override_settings(MIDDLEWARE_CLASSES=[])
    def test_no_security_middleware(self):
        self.assertEqual(
            self.func(), set(["SECURITY_MIDDLEWARE_NOT_INSTALLED"]))


    @override_settings(
        MIDDLEWARE_CLASSES=["djangosecure.middleware.SecurityMiddleware"])
    def test_with_security_middleware(self):
        self.assertEqual(self.func(), set())



class CheckStrictTransportSecurityTest(TestCase):
    @property
    def func(self):
        from djangosecure.check.djangosecure import check_sts
        return check_sts


    @override_settings(SECURE_STS_SECONDS=0)
    def test_no_sts(self):
        self.assertEqual(
            self.func(), set(["STRICT_TRANSPORT_SECURITY_NOT_ENABLED"]))


    @override_settings(SECURE_STS_SECONDS=3600)
    def test_with_sts(self):
        self.assertEqual(self.func(), set())



class CheckFrameDenyTest(TestCase):
    @property
    def func(self):
        from djangosecure.check.djangosecure import check_frame_deny
        return check_frame_deny


    @override_settings(SECURE_FRAME_DENY=False)
    def test_no_sts(self):
        self.assertEqual(
            self.func(), set(["FRAME_DENY_NOT_ENABLED"]))


    @override_settings(SECURE_FRAME_DENY=True)
    def test_with_sts(self):
        self.assertEqual(self.func(), set())



class CheckSSLRedirectTest(TestCase):
    @property
    def func(self):
        from djangosecure.check.djangosecure import check_ssl_redirect
        return check_ssl_redirect


    @override_settings(SECURE_SSL_REDIRECT=False)
    def test_no_sts(self):
        self.assertEqual(
            self.func(), set(["SSL_REDIRECT_NOT_ENABLED"]))


    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_with_sts(self):
        self.assertEqual(self.func(), set())



class ConfTest(TestCase):
    def test_no_fallback(self):
        """
        Accessing a setting without a default value raises in
        ImproperlyConfigured.

        """
        from djangosecure.conf import conf

        self.assertRaises(ImproperlyConfigured, getattr, conf, "HAS_NO_DEFAULT")