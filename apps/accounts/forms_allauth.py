from allauth.account.forms import ChangePasswordForm, SignupForm
from django import forms

from .models import Profile


class CustomSignupForm(SignupForm):
    phone = forms.CharField(label='موبایل', max_length=32, required=False)

    def save(self, request):
        user = super().save(request)
        phone = self.cleaned_data.get('phone', '').strip()
        if phone:
            # ensure profile exists and set phone
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.phone = phone
            profile.save(update_fields=['phone'])
        return user


class CustomChangePasswordForm(ChangePasswordForm):
    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('password1')
        if new_password and self.user and self.user.check_password(new_password):
            self.add_error('password1', 'شما نمی‌توانید رمز قبلی‌تان را دوباره انتخاب کنید.')
        return cleaned_data
