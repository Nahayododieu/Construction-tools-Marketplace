from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Product
from .models import Comment
from .models import Message
from .models import Report
from .models import Share


class RegularUserSignupForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password1', 'password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data.get('first_name', '')
        user.last_name = self.cleaned_data.get('last_name', '')
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
        return user


class EmailOrUsernameAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label='Username or Email',
        widget=forms.TextInput(attrs={'autofocus': True, 'placeholder': 'Enter username or email'})
    )

    def clean(self):
        login_value = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if login_value and password:
            username = login_value
            if '@' in login_value:
                matched_user = User.objects.filter(email__iexact=login_value).first()
                if matched_user:
                    username = matched_user.username

            self.user_cache = authenticate(
                self.request,
                username=username,
                password=password,
            )

            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['image', 'title', 'slug', 'description', 'price', 'category', 'city', 'stock_quantity', 'is_featured', 'status']

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Add a comment...'})
        }


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['receiver', 'ad', 'subject', 'body']
        widgets = {
            'body': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Write your message...'})
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['receiver'].queryset = User.objects.exclude(id=user.id)
        self.fields['ad'].required = False


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ['report_type', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Please provide details about why you are reporting this advertisement...'})
        }


class ShareForm(forms.Form):
    share_method = forms.ChoiceField(
        choices=Share.SHARE_METHODS,
        widget=forms.HiddenInput()
    )


class OrderForm(forms.Form):
    PAYMENT_CHOICES = [
        ('credit_card', 'Credit Card'),
        ('paypal', 'PayPal'),
        ('bank_transfer', 'Bank Transfer'),
        ('cod', 'Cash on Delivery'),
    ]

    buyer_name = forms.CharField(max_length=200, label='Full Name')
    buyer_email = forms.EmailField(label='Email Address')
    payment_method = forms.ChoiceField(choices=PAYMENT_CHOICES, label='Payment Method')
    quantity = forms.IntegerField(min_value=1, initial=1, label='Quantity')
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3}), label='Additional Notes (optional)')


class CancelOrderForm(forms.Form):
    cancellation_reason = forms.CharField(
        required=False,
        label='Please help us know why you canceled the order to improve',
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'Optional feedback to help us improve your experience.'
        })
    )


AdvertisementForm = ProductForm

