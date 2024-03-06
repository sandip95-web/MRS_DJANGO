from django.contrib.auth.models import User
from django import forms
from django.core.exceptions import ValidationError
from .models import *
from django.core.validators import RegexValidator,EmailValidator
import re

class UserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def clean_username(self):
        username = self.cleaned_data.get('username')
        
        # Regular expression validator to check if the username contains at least one letter
        regex = RegexValidator(regex=r'^[a-zA-Z]+$', message="Username must contain only letters.")
        regex(username)  # This line will raise ValidationError if the username does not match the regular expression
        
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        
        # Custom email validation using regular expressions
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            raise ValidationError("Enter a valid email address.")
        
        if User.objects.filter(email=email).exists():
            raise ValidationError("This email is already in use. Please use a different email.")
        
        return email

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if password:
            # Add your custom password validation logic here
            # For example, you might want to enforce a minimum length
            min_length = 8
            if len(password) < min_length:
                raise ValidationError(f"Password must be at least {min_length} characters long.")
        return password
