"""
This file will test through the LMS some of the PasswordHistory features
"""
import json
from mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from django.core.urlresolvers import reverse

from freezegun import freeze_time

from student.models import PasswordHistory
from courseware.tests.helpers import LoginEnrollmentTestCase


@patch.dict("django.conf.settings.FEATURES", {'ADVANCED_SECURITY': True})
class TestPasswordHistory(LoginEnrollmentTestCase):
    """
    Go through some of the PasswordHistory use cases
    """

    def login(self, email, password, should_succeed=True, err_msg_check=None):
        """
        Override the base implementation so we can do appropriate asserts
        """
        resp = self.client.post(reverse('login'), {'email': email, 'password': password})
        data = json.loads(resp.content)

        self.assertEqual(resp.status_code, 200)
        if should_succeed:
            self.assertTrue(data['success'])
        else:
            self.assertFalse(data['success'])
            if err_msg_check:
                self.assertIn(err_msg_check, data['value'])

    def setup_user(self, is_staff=False):
        """
        Override the base implementation to randomize the email
        """
        email = 'foo_{0}@test.com'.format(uuid4().hex[:8])
        password = 'bar'
        username = 'test_{0}'.format(uuid4().hex[:8])
        self.create_account(username, email, password)
        self.activate_user(email)

        # manually twiddle the is_staff bit, if needed
        if is_staff:
            user = User.objects.get(email=email)
            user.is_staff = True
            user.save()

        return email, password

    def _update_password(self, email, new_password):
        """
        Helper method to reset a password
        """
        user = User.objects.get(email=email)
        user.set_password(new_password)
        user.save()
        history = PasswordHistory()
        history.create(user)

    @patch.dict("django.conf.settings.ADVANCED_SECURITY_CONFIG", {'MIN_DAYS_FOR_STAFF_ACCOUNTS_PASSWORD_RESETS': None})
    @patch.dict("django.conf.settings.ADVANCED_SECURITY_CONFIG", {'MIN_DAYS_FOR_STUDENT_ACCOUNTS_PASSWORD_RESETS': None})
    def test_no_forced_password_change(self):
        """
        Makes sure default behavior is correct when we don't have this turned on
        """

        email, password = self.setup_user()
        self.login(email, password)

        email, password = self.setup_user(is_staff=True)
        self.login(email, password)

    @patch.dict("django.conf.settings.ADVANCED_SECURITY_CONFIG", {'MIN_DAYS_FOR_STAFF_ACCOUNTS_PASSWORD_RESETS': 1})
    @patch.dict("django.conf.settings.ADVANCED_SECURITY_CONFIG", {'MIN_DAYS_FOR_STUDENT_ACCOUNTS_PASSWORD_RESETS': 5})
    def test_forced_password_change(self):
        """
        Make sure password are viewed as expired in LMS after the policy time has elapsed
        """

        student_email, student_password = self.setup_user()
        staff_email, staff_password = self.setup_user(is_staff=True)

        self.login(student_email, student_password)
        self.login(staff_email, staff_password)

        staff_reset_time = timezone.now() + timedelta(days=1)
        with freeze_time(staff_reset_time):
            self.login(student_email, student_password)

            # staff should fail because password expired
            self.login(staff_email, staff_password, should_succeed=False,
                       err_msg_check="Your password has expired due to password policy on this account")

            # if we reset the password, we should be able to log in
            self._update_password(staff_email, "updated")
            self.login(staff_email, "updated")

        student_reset_time = timezone.now() + timedelta(days=5)
        with freeze_time(student_reset_time):
            # Both staff and student logins should fail because user must
            # reset the password

            self.login(student_email, student_password, should_succeed=False,
                       err_msg_check="Your password has expired due to password policy on this account")
            self._update_password(student_email, "updated")
            self.login(student_email, "updated")

            self.login(staff_email, staff_password, should_succeed=False,
                       err_msg_check="Your password has expired due to password policy on this account")
            self._update_password(staff_email, "updated2")
            self.login(staff_email, "updated2")
