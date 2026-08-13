from datetime import datetime

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import RequestFactory, TestCase
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from django.utils import timezone

from cigars.admin import GuideConfigurationAdmin, UserGuideProgressAdmin
from cigars.models import GuideConfiguration, User, UserGuideProgress


class GuideModelTest(TestCase):
    def test_configuration_is_singleton_and_version_must_be_positive(self):
        first, _ = GuideConfiguration.objects.update_or_create(
            pk=1, defaults={'version': 1, 'auto_show_enabled': True}
        )
        second, created = GuideConfiguration.objects.update_or_create(
            pk=1, defaults={'version': 3, 'auto_show_enabled': False}
        )

        self.assertEqual(GuideConfiguration.objects.count(), 1)
        self.assertFalse(created)
        first.refresh_from_db()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.version, 3)
        self.assertFalse(first.auto_show_enabled)

        invalid = GuideConfiguration(version=0)
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        with self.assertRaises(IntegrityError):
            GuideConfiguration.objects.filter(pk=1).update(version=0)

    def test_database_rejects_non_singleton_primary_key(self):
        with self.assertRaises(IntegrityError):
            GuideConfiguration.objects.bulk_create([GuideConfiguration(id=2, version=1)])

    def test_lazy_initialization_is_stable_when_configuration_is_absent(self):
        GuideConfiguration.objects.all().delete()
        user = User.objects.create_user('guide-lazy-user', is_staff=True)
        from cigars.guide_views import _summary

        self.assertEqual(_summary(user)['version'], 1)
        self.assertEqual(_summary(user)['version'], 1)
        self.assertEqual(GuideConfiguration.objects.count(), 1)

    def test_progress_is_one_to_one_with_user(self):
        user = User.objects.create_user('guide-model-user')
        progress = UserGuideProgress.objects.create(user=user)

        self.assertEqual(progress.completed_version, 0)
        self.assertFalse(progress.force_show_next_time)
        self.assertIsNone(progress.completed_at)
        with self.assertRaises(Exception):
            UserGuideProgress.objects.create(user=user)


class GuideApiTest(TestCase):
    def setUp(self):
        self.config, _ = GuideConfiguration.objects.update_or_create(
            pk=1, defaults={'version': 1, 'auto_show_enabled': True}
        )
        self.staff = User.objects.create_user('guide-staff', password='pass', is_staff=True)
        self.operator = User.objects.create_user('guide-operator', password='pass', is_staff=False)

    def get(self, url):
        self.client.force_login(self.staff)
        return self.client.get(url)

    def post(self, url):
        self.client.force_login(self.staff)
        return self.client.post(url, data={}, content_type='application/json')

    def test_status_requires_authentication_and_staff(self):
        response = self.client.get(reverse('guide_status'))
        self.assertEqual(response.status_code, 401)

        self.client.force_login(self.operator)
        response = self.client.get(reverse('guide_status'))
        self.assertEqual(response.status_code, 403)

    def test_new_staff_user_needs_current_guide(self):
        response = self.get(reverse('guide_status'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'version': 1,
            'auto_show_enabled': True,
            'should_show': True,
            'completed_version': 0,
            'force_show_next_time': False,
        })

    def test_complete_is_idempotent_and_clears_force(self):
        progress = UserGuideProgress.objects.create(
            user=self.staff, completed_version=0, force_show_next_time=True
        )

        first = self.post(reverse('guide_complete'))
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()['completed'])
        progress.refresh_from_db()
        completed_at = progress.completed_at
        self.assertEqual(progress.completed_version, 1)
        self.assertFalse(progress.force_show_next_time)
        self.assertIsNotNone(completed_at)

        second = self.post(reverse('guide_complete'))
        self.assertEqual(second.status_code, 200)
        progress.refresh_from_db()
        self.assertEqual(progress.completed_version, 1)
        self.assertFalse(progress.force_show_next_time)
        self.assertEqual(progress.completed_at, completed_at)

    def test_version_upgrade_requires_new_version(self):
        UserGuideProgress.objects.create(user=self.staff, completed_version=1)
        self.config.version = 2
        self.config.save(update_fields=['version'])

        response = self.get(reverse('guide_status'))

        self.assertTrue(response.json()['should_show'])
        self.assertEqual(response.json()['completed_version'], 1)
        self.assertEqual(response.json()['version'], 2)

    def test_global_disable_suppresses_auto_show_even_after_replay(self):
        UserGuideProgress.objects.create(user=self.staff, completed_version=1)
        self.config.auto_show_enabled = False
        self.config.save(update_fields=['auto_show_enabled'])

        replay = self.post(reverse('guide_replay'))
        self.assertEqual(replay.status_code, 200)
        progress = UserGuideProgress.objects.get(user=self.staff)
        self.assertTrue(progress.force_show_next_time)

        response = self.get(reverse('guide_status'))
        self.assertFalse(response.json()['should_show'])
        self.assertTrue(response.json()['force_show_next_time'])

    def test_replay_forces_current_user_without_changing_completion(self):
        UserGuideProgress.objects.create(user=self.staff, completed_version=1)

        response = self.post(reverse('guide_replay'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['force_show_next_time'])
        progress = UserGuideProgress.objects.get(user=self.staff)
        self.assertEqual(progress.completed_version, 1)
        self.assertTrue(progress.force_show_next_time)

    def test_complete_and_replay_require_staff(self):
        self.client.force_login(self.operator)
        for name in ('guide_complete', 'guide_replay'):
            response = self.client.post(reverse(name), data={}, content_type='application/json')
            self.assertEqual(response.status_code, 403)

    def test_mutations_require_csrf_token(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.staff)
        for name in ('guide_complete', 'guide_replay'):
            response = client.post(reverse(name), data={}, content_type='application/json')
            self.assertEqual(response.status_code, 403)

        client.get(reverse('api_auth_me'))
        token = client.cookies['csrftoken'].value
        for name in ('guide_complete', 'guide_replay'):
            response = client.post(
                reverse(name), data={}, content_type='application/json',
                HTTP_X_CSRFTOKEN=token,
            )
            self.assertEqual(response.status_code, 200)

    def test_api_me_embeds_guide_summary_for_staff(self):
        UserGuideProgress.objects.create(user=self.staff, completed_version=1)

        self.client.force_login(self.staff)
        response = self.client.get(reverse('api_auth_me'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user']['guide'], {
            'version': 1,
            'auto_show_enabled': True,
            'should_show': False,
            'completed_version': 1,
            'force_show_next_time': False,
        })

    def test_api_me_omits_guide_for_anonymous_user(self):
        response = self.client.get(reverse('api_auth_me'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['authenticated'])
        self.assertNotIn('guide', response.json())

    def test_api_me_omits_guide_for_non_staff_user(self):
        self.client.force_login(self.operator)
        response = self.client.get(reverse('api_auth_me'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('guide', response.json()['user'])

    def test_staff_login_embeds_current_guide_summary(self):
        UserGuideProgress.objects.create(user=self.staff, completed_version=0)

        response = self.client.post(reverse('api_login'), {
            'username': 'guide-staff', 'password': 'pass',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user']['guide'], {
            'version': 1,
            'auto_show_enabled': True,
            'should_show': True,
            'completed_version': 0,
            'force_show_next_time': False,
        })

    def test_non_staff_login_does_not_create_guide_progress(self):
        response = self.client.post(reverse('api_login'), {
            'username': 'guide-operator', 'password': 'pass',
        })

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('guide', response.json()['user'])
        self.assertFalse(UserGuideProgress.objects.filter(user=self.operator).exists())


class GuideAdminTest(TestCase):
    def test_only_guide_settings_are_editable(self):
        config_admin = admin.site._registry[GuideConfiguration]
        progress_admin = admin.site._registry[UserGuideProgress]

        self.assertIsInstance(config_admin, GuideConfigurationAdmin)
        self.assertIsInstance(progress_admin, UserGuideProgressAdmin)
        self.assertEqual(config_admin.fields, ('version', 'auto_show_enabled'))
        self.assertIn('completed_version', progress_admin.readonly_fields)
        self.assertIn('completed_at', progress_admin.readonly_fields)
        self.assertEqual(progress_admin.fields, (
            'user', 'completed_version', 'force_show_next_time', 'completed_at'
        ))

    def test_add_permission_requires_model_permission_and_singleton_slot(self):
        request = RequestFactory().get('/admin/')
        request.user = User.objects.create_user('admin-permission', is_staff=True)
        config_admin = admin.site._registry[GuideConfiguration]
        self.assertFalse(config_admin.has_add_permission(request))
