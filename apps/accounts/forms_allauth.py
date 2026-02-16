from allauth.account.forms import SignupForm
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
