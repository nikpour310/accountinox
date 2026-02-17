from allauth.account.adapter import DefaultAccountAdapter


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
