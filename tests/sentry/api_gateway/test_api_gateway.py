from urllib.parse import urlencode

import responses
from django.test import override_settings
from django.urls import reverse

from sentry.silo import SiloMode
from sentry.testutils.helpers.api_gateway import ApiGatewayTestCase, verify_request_params
from sentry.testutils.helpers.response import close_streaming_response
from sentry.utils import json


class ApiGatewayTest(ApiGatewayTestCase):
    @override_settings(SILO_MODE=SiloMode.CONTROL)
    @responses.activate
    def test_simple(self):
        query_params = dict(foo="test", bar=["one", "two"])
        headers = dict(example="this")
        responses.add_callback(
            responses.GET,
            f"http://us.internal.sentry.io/organizations/{self.organization.slug}/region/",
            verify_request_params(query_params, headers),
        )

        base_url = reverse("region-endpoint", kwargs={"organization_slug": self.organization.slug})
        encoded_params = urlencode(query_params, doseq=True)
        url = f"{base_url}?{encoded_params}"
        with override_settings(MIDDLEWARE=tuple(self.middleware)):
            resp = self.client.get(url, headers=headers)
        assert resp.status_code == 200, resp.content
        resp_json = json.loads(close_streaming_response(resp))
        assert resp_json["proxy"]

    @responses.activate
    def test_proxy_check_org_slug_url(self):
        """Test the logic of when a request should be proxied"""
        responses.add(
            responses.GET,
            f"http://us.internal.sentry.io/organizations/{self.organization.slug}/region/",
            json={"proxy": True},
        )
        responses.add(
            responses.GET,
            f"http://us.internal.sentry.io/organizations/{self.organization.slug}/control/",
            json={"proxy": True},
        )

        region_url = reverse(
            "region-endpoint", kwargs={"organization_slug": self.organization.slug}
        )
        control_url = reverse(
            "control-endpoint", kwargs={"organization_slug": self.organization.slug}
        )

        with override_settings(SILO_MODE=SiloMode.CONTROL, MIDDLEWARE=tuple(self.middleware)):
            resp = self.client.get(region_url)
            assert resp.status_code == 200
            resp_json = json.loads(close_streaming_response(resp))
            assert resp_json["proxy"]

            resp = self.client.get(control_url)
            assert resp.status_code == 200
            assert not resp.data["proxy"]

        with override_settings(SILO_MODE=SiloMode.REGION, MIDDLEWARE=tuple(self.middleware)):
            resp = self.client.get(region_url)
            assert resp.status_code == 200
            assert not resp.data["proxy"]

    @responses.activate
    def test_proxy_check_region_pinned_url(self):
        responses.add(
            responses.GET,
            "http://us.internal.sentry.io/builtin-symbol-sources/",
            json={"proxy": True},
        )

        # No /api/0 as we only include sentry.api.urls.urlpatterns
        # and not sentry.web.urls which includes the version prefix
        region_pinned = "/builtin-symbol-sources/"
        control_url = reverse(
            "control-endpoint", kwargs={"organization_slug": self.organization.slug}
        )

        with override_settings(
            SILO_MODE=SiloMode.CONTROL,
            MIDDLEWARE=tuple(self.middleware),
            SENTRY_MONOLITH_REGION="us",
        ):
            resp = self.client.get(region_pinned)
            assert resp.status_code == 200
            resp_json = json.loads(close_streaming_response(resp))
            assert resp_json["proxy"]

            resp = self.client.get(control_url)
            assert resp.status_code == 200
            assert not resp.data["proxy"]

    @responses.activate
    def test_proxy_check_region_pinned_url_with_params(self):
        responses.add(
            responses.GET,
            "http://us.internal.sentry.io/relays/register/",
            json={"proxy": True},
        )
        responses.add(
            responses.GET,
            "http://us.internal.sentry.io/relays/abc123/",
            json={"proxy": True, "details": True},
        )

        with override_settings(
            SILO_MODE=SiloMode.CONTROL,
            MIDDLEWARE=tuple(self.middleware),
            SENTRY_MONOLITH_REGION="us",
        ):
            resp = self.client.get("/relays/register/")
            assert resp.status_code == 200
            resp_json = json.loads(close_streaming_response(resp))
            assert resp_json["proxy"]

            resp = self.client.get("/relays/abc123/")
            assert resp.status_code == 200
            resp_json = json.loads(close_streaming_response(resp))
            assert resp_json["proxy"]
            assert resp_json["details"]
