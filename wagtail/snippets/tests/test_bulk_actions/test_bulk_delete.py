from django.contrib.admin.utils import quote
from django.contrib.auth.models import Permission
from django.http import HttpRequest, HttpResponse
from django.test import TestCase
from django.urls import reverse
from django.utils.http import urlencode

from wagtail.snippets.bulk_actions.delete import DeleteBulkAction
from wagtail.test.testapp.models import (
    Advert,
    FullFeaturedSnippet,
    VariousOnDeleteModel,
)
from wagtail.test.utils import WagtailTestUtils


class TestSnippetDeleteView(WagtailTestUtils, TestCase):
    def setUp(self):
        self.snippet_model = FullFeaturedSnippet

        # create a set of test snippets
        self.test_snippets = [
            self.snippet_model.objects.create(
                text=f"Title-{i}",
            )
            for i in range(1, 6)
        ]

        self.user = self.login()
        self.url = (
            reverse(
                "wagtail_bulk_action",
                args=(
                    self.snippet_model._meta.app_label,
                    self.snippet_model._meta.model_name,
                    "delete",
                ),
            )
            + "?"
        )

    def get_url(self, items=()):
        items = items or self.test_snippets
        return self.url + "&".join(f"id={item.pk}" for item in items)

    def test_simple(self):
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "wagtailsnippets/bulk_actions/confirm_bulk_delete.html"
        )
        self.assertTemplateUsed(response, "wagtailadmin/shared/header.html")
        self.assertEqual(response.context["header_icon"], "cog")
        self.assertContains(response, "icon icon-cog", count=1)

    def test_get_single_delete(self):
        item = self.test_snippets[0]
        response = self.client.get(self.get_url(items=(item,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "wagtailsnippets/bulk_actions/confirm_bulk_delete.html"
        )
        self.assertTemplateUsed(response, "wagtailadmin/shared/header.html")
        self.assertEqual(response.context["header_icon"], "cog")
        self.assertContains(response, "icon icon-cog", count=1)
        self.assertContains(
            response,
            "<title>Delete full-featured snippet - Title-1 - Wagtail</title>",
            html=True,
        )
        self.assertContains(
            response,
            reverse(
                self.snippet_model.snippet_viewset.get_url_name("usage"),
                args=(quote(item.pk),),
            ),
        )
        self.assertContains(
            response,
            "This full-featured snippet is referenced 0 times.",
        )

    def test_bulk_delete(self):
        response = self.client.post(self.get_url())

        # Should redirect back to index
        self.assertEqual(response.status_code, 302)

        # Check that the users were deleted
        for snippet in self.test_snippets:
            self.assertFalse(self.snippet_model.objects.filter(pk=snippet.pk).exists())

    def test_delete_with_limited_permissions(self):
        self.user.is_superuser = False
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="wagtailadmin", codename="access_admin"
            )
        )
        self.user.save()

        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)

        html = response.content.decode()
        self.assertInHTML(
            "<p>You don't have permission to delete these full-featured snippets</p>",
            html,
        )

        for snippet in self.test_snippets:
            self.assertInHTML(f"<li>{snippet.text}</li>", html)

        response = self.client.post(self.get_url())
        # User should be redirected back to the index
        self.assertEqual(response.status_code, 302)

        # Snippets should not be deleted
        for snippet in self.test_snippets:
            self.assertTrue(self.snippet_model.objects.filter(pk=snippet.pk).exists())

    def test_before_bulk_action_hook_get(self):
        with self.register_hook(
            "before_bulk_action", lambda *args: HttpResponse("Overridden!")
        ):
            response = self.client.get(self.get_url())

        self.assertEqual(response.status_code, 200)

        # The hook was not called
        self.assertNotEqual(response.content, b"Overridden!")

        # The instances were not deleted
        self.assertQuerySetEqual(
            self.snippet_model.objects.filter(
                pk__in=[snippet.pk for snippet in self.test_snippets]
            ),
            self.test_snippets,
            ordered=False,
        )

    def test_before_bulk_action_hook_post(self):
        def hook_func(request, action_type, instances, action_class_instance):
            self.assertIsInstance(request, HttpRequest)
            self.assertEqual(action_type, "delete")
            self.assertEqual(set(instances), set(self.test_snippets))
            self.assertIsInstance(action_class_instance, DeleteBulkAction)
            return HttpResponse("Overridden!")

        with self.register_hook("before_bulk_action", hook_func):
            response = self.client.post(self.get_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"Overridden!")

        # Request intercepted before the snippets were deleted
        self.assertQuerySetEqual(
            self.snippet_model.objects.filter(
                pk__in=[snippet.pk for snippet in self.test_snippets]
            ),
            self.test_snippets,
            ordered=False,
        )

    def test_after_bulk_action_hook(self):
        def hook_func(request, action_type, instances, action_class_instance):
            self.assertIsInstance(request, HttpRequest)
            self.assertEqual(action_type, "delete")
            self.assertEqual(set(instances), set(self.test_snippets))
            self.assertIsInstance(action_class_instance, DeleteBulkAction)
            return HttpResponse("Overridden!")

        with self.register_hook("after_bulk_action", hook_func):
            response = self.client.post(self.get_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"Overridden!")

        # Request intercepted after the snippets were deleted
        self.assertFalse(
            self.snippet_model.objects.filter(
                pk__in=[snippet.pk for snippet in self.test_snippets]
            ).exists()
        )

    # Also tests that the {before,after}_delete_snippet hooks are called.
    # These hooks have existed since before bulk actions were introduced,
    # so we need to make sure they still work.

    def test_before_delete_snippet_hook_get(self):
        def hook_func(request, instances):
            self.assertIsInstance(request, HttpRequest)
            self.assertEqual(set(instances), set(self.test_snippets))
            return HttpResponse("Overridden!")

        with self.register_hook("before_delete_snippet", hook_func):
            response = self.client.get(self.get_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"Overridden!")

        # Request intercepted before the snippets were deleted
        self.assertQuerySetEqual(
            self.snippet_model.objects.filter(
                pk__in=[snippet.pk for snippet in self.test_snippets]
            ),
            self.test_snippets,
            ordered=False,
        )

    def test_before_delete_snippet_hook_post(self):
        def hook_func(request, instances):
            self.assertIsInstance(request, HttpRequest)
            self.assertEqual(set(instances), set(self.test_snippets))
            return HttpResponse("Overridden!")

        with self.register_hook("before_delete_snippet", hook_func):
            response = self.client.post(self.get_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"Overridden!")

        # Request intercepted before the snippets were deleted
        self.assertQuerySetEqual(
            self.snippet_model.objects.filter(
                pk__in=[snippet.pk for snippet in self.test_snippets]
            ),
            self.test_snippets,
            ordered=False,
        )

    def test_after_delete_snippet_hook(self):
        def hook_func(request, instances):
            self.assertIsInstance(request, HttpRequest)
            self.assertEqual(set(instances), set(self.test_snippets))
            return HttpResponse("Overridden!")

        with self.register_hook("after_delete_snippet", hook_func):
            response = self.client.post(self.get_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"Overridden!")

        # Request intercepted after the snippets were deleted
        self.assertFalse(
            self.snippet_model.objects.filter(
                pk__in=[snippet.pk for snippet in self.test_snippets]
            ).exists()
        )


class TestProtectedBulkDeleteView(WagtailTestUtils, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.snippet_model = Advert
        cls.test_snippets = [
            cls.snippet_model.objects.create(text=f"Title-{i}") for i in range(1, 6)
        ]
        cls.url = reverse(
            "wagtail_bulk_action",
            args=(
                cls.snippet_model._meta.app_label,
                cls.snippet_model._meta.model_name,
                "delete",
            ),
        )
        cls.query_params = {
            "next": reverse("wagtailsnippets_tests_advert:list"),
            "id": [item.pk for item in cls.test_snippets],
        }
        cls.url += "?" + urlencode(cls.query_params, doseq=True)

    def setUp(self):
        self.user = self.login()

    def test_delete_get_with_protected_reference(self):
        protected = self.test_snippets[0]
        with self.captureOnCommitCallbacks(execute=True):
            VariousOnDeleteModel.objects.create(
                text="Undeletable",
                on_delete_protect=protected,
            )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        soup = self.get_soup(response.content)
        main = soup.select_one("main")
        usage_link = main.find(
            "a",
            href=reverse(
                "wagtailsnippets_tests_advert:usage",
                args=[quote(protected.pk)],
            )
            + "?describe_on_delete=1",
        )
        self.assertIsNotNone(usage_link)
        self.assertEqual(usage_link.text.strip(), "This advert is referenced 1 time.")
        self.assertContains(
            response,
            "One or more references to this advert prevent it from being deleted.",
        )
        submit_button = main.select_one("form button[type=submit]")
        self.assertIsNone(submit_button)
        back_button = main.find("a", href=reverse("wagtailsnippets_tests_advert:list"))
        self.assertIsNotNone(back_button)
        self.assertEqual(back_button.text.strip(), "Go back")

    def test_delete_post_with_protected_reference(self):
        protected = self.test_snippets[0]
        with self.captureOnCommitCallbacks(execute=True):
            VariousOnDeleteModel.objects.create(
                text="Undeletable",
                on_delete_protect=protected,
            )
        response = self.client.post(self.url)

        # Should throw a PermissionDenied error and redirect to the dashboard
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("wagtailadmin_home"))
        self.assertEqual(
            response.context["message"],
            "Sorry, you do not have permission to access this area.",
        )

        # Check that the snippet is still here
        self.assertTrue(Advert.objects.filter(pk=protected.pk).exists())
