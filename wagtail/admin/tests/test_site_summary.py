from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from wagtail.admin.site_summary import PagesSummaryItem
from wagtail.models import GroupPagePermission, Page, Site
from wagtail.test.testapp.models import SimplePage
from wagtail.test.utils import WagtailTestUtils


class TestPagesSummary(WagtailTestUtils, TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.test_page = SimplePage(title="test", slug="test", content="test")
        cls.wagtail_root = Page.get_first_root_node()
        cls.wagtail_root.add_child(instance=cls.test_page)

        cls.test_page_group = Group.objects.create(name="Test page")

    @classmethod
    def tearDownClass(cls):
        cls.test_page.delete()
        cls.test_page_group.delete()

        super().tearDownClass()

    def setUp(self):
        self.user = self.login()
        self.request = self.client.get("/").wsgi_request

    def assertSummaryContains(self, content):
        summary = PagesSummaryItem(self.request).render_html()
        self.assertIn(content, summary)

    def assertSummaryContainsLinkToPage(self, page_pk):
        self.assertSummaryContains(reverse("wagtailadmin_explore", args=[page_pk]))

    def test_user_with_page_permissions_is_shown_panel(self):
        self.assertTrue(PagesSummaryItem(self.request).is_shown())

    def test_single_site_summary_links_to_site_root(self):
        self.assertEqual(Site.objects.count(), 1)
        site = Site.objects.first()
        self.assertSummaryContainsLinkToPage(site.root_page.pk)

    def test_multiple_sites_summary_links_to_wagtail_root(self):
        Site.objects.create(hostname="foo.com", root_page=self.wagtail_root)
        self.assertSummaryContainsLinkToPage(self.wagtail_root.pk)

    def test_no_sites_summary_links_to_wagtail_root(self):
        Site.objects.all().delete()
        self.assertSummaryContainsLinkToPage(self.wagtail_root.pk)

    def test_summary_includes_page_count_without_wagtail_root(self):
        self.assertSummaryContains(f"{Page.objects.count() - 1} Pages")

    def test_summary_shows_zero_pages_if_none_exist_except_wagtail_root(self):
        Page.objects.exclude(pk=self.wagtail_root.pk).delete()
        self.assertSummaryContains("0 Pages")

    def test_user_with_no_page_permissions_is_not_shown_panel(self):
        self.user.is_superuser = False
        self.user.save()
        self.assertFalse(PagesSummaryItem(self.request).is_shown())

    def test_user_with_limited_page_permissions(self):
        permissions = {"add", "change", "publish", "bulk_delete", "lock", "unlock"}
        self.user.is_superuser = False
        self.user.save()
        self.user.groups.add(self.test_page_group)

        for permission in permissions:
            with self.subTest(permission=permission):
                permission_obj = GroupPagePermission.objects.create(
                    group=self.test_page_group,
                    page=self.test_page,
                    permission_type=permission,
                )
                # Should link to the permission's page rather than Wagtail's root
                self.assertSummaryContainsLinkToPage(self.test_page.pk)
                # Should show the correct page count
                self.assertSummaryContains("1 Page")
                permission_obj.delete()
                self.test_page_group.page_permissions.all().delete()
