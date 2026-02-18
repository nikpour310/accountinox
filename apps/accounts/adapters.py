from allauth.account.adapter import DefaultAccountAdapter
from django.urls import reverse


class NoConfirmationOnLoginAdapter(DefaultAccountAdapter):
    """Override to avoid sending confirmation emails when users simply log in.

    allauth calls `send_confirmation_mail(request, emailconfirmation, signup)` in
    several places. We only want to send confirmation mail when `signup` is True
    (i.e., a new registration), not during login or other flows.
    """

    def send_confirmation_mail(self, request, emailconfirmation, signup):
        if not signup:
            # Skip sending confirmation when not part of signup flow
            return
        return super().send_confirmation_mail(request, emailconfirmation, signup)

    def get_password_change_redirect_url(self, request):
        """
        Redirect back to password management page with an explicit success flag
        so the UI can show a persistent inline result (not only toast).
        """
        base_url = reverse('account_change_password')
        separator = '&' if '?' in base_url else '?'
        return f'{base_url}{separator}password_updated=1'
