from django.contrib.auth import get_user_model

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class AccountinoxSocialAccountAdapter(DefaultSocialAccountAdapter):
    @staticmethod
    def _extract_email(sociallogin) -> str:
        user = getattr(sociallogin, "user", None)
        if user:
            email = (getattr(user, "email", "") or "").strip().lower()
            if email:
                return email

        for email_address in getattr(sociallogin, "email_addresses", []) or []:
            email = (getattr(email_address, "email", "") or "").strip().lower()
            if email:
                return email

        account = getattr(sociallogin, "account", None)
        extra_data = getattr(account, "extra_data", {}) or {}
        return (extra_data.get("email") or "").strip().lower()

    @staticmethod
    def _email_is_available(user, email: str) -> bool:
        if not email:
            return False
        User = get_user_model()
        qs = User.objects.filter(email__iexact=email)
        if user and getattr(user, "pk", None):
            qs = qs.exclude(pk=user.pk)
        return not qs.exists()

    def _sync_missing_user_email(self, sociallogin, persist: bool = False) -> None:
        user = getattr(sociallogin, "user", None)
        if not user:
            return

        current_email = (getattr(user, "email", "") or "").strip()
        if current_email:
            return

        extracted_email = self._extract_email(sociallogin)
        if not extracted_email:
            return

        if not self._email_is_available(user, extracted_email):
            return

        user.email = extracted_email
        if persist and getattr(user, "pk", None):
            user.save(update_fields=["email"])

    def populate_user(self, request, sociallogin, data):
        if not data.get("email"):
            extracted_email = self._extract_email(sociallogin)
            if extracted_email:
                data = dict(data)
                data["email"] = extracted_email
        return super().populate_user(request, sociallogin, data)

    def pre_social_login(self, request, sociallogin):
        super().pre_social_login(request, sociallogin)
        self._sync_missing_user_email(sociallogin, persist=True)

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form=form)
        self._sync_missing_user_email(sociallogin, persist=True)
        return user
