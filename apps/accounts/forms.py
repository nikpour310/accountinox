from django import forms

from .models import OrderAddress, Profile


class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=False, label='نام')
    last_name = forms.CharField(max_length=150, required=False, label='نام خانوادگی')
    email = forms.EmailField(required=False, label='ایمیل')
    username = forms.CharField(max_length=150, required=False, label='شناسه کاربری', disabled=True)

    class Meta:
        model = Profile
        fields = ('phone',)
        labels = {'phone': 'موبایل'}

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['first_name'].initial = user.first_name
        self.fields['last_name'].initial = user.last_name
        self.fields['email'].initial = user.email
        self.fields['username'].initial = user.username
        for field_name in ('first_name', 'last_name', 'email', 'username', 'phone'):
            self.fields[field_name].widget.attrs.setdefault('class', 'ui-input')

    def save(self, commit=True):
        profile = super().save(commit=False)
        self.user.first_name = self.cleaned_data.get('first_name', '').strip()
        self.user.last_name = self.cleaned_data.get('last_name', '').strip()
        self.user.email = self.cleaned_data.get('email', '').strip()
        if commit:
            self.user.save(update_fields=['first_name', 'last_name', 'email'])
            profile.user = self.user
            profile.save()
        return profile


class OrderAddressForm(forms.ModelForm):
    class Meta:
        model = OrderAddress
        fields = (
            'label',
            'full_name',
            'phone',
            'province',
            'city',
            'street_address',
            'postal_code',
            'is_default',
        )
        labels = {
            'label': 'عنوان',
            'full_name': 'نام تحویل‌گیرنده',
            'phone': 'شماره موبایل',
            'province': 'استان',
            'city': 'شهر',
            'street_address': 'نشانی کامل',
            'postal_code': 'کد پستی',
            'is_default': 'نشانی پیش‌فرض',
        }
        widgets = {
            'street_address': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name == 'is_default':
                field.widget.attrs.setdefault('class', 'h-4 w-4')
            else:
                field.widget.attrs.setdefault('class', 'ui-input')
