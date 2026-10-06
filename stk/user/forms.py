from quart_security.forms import ChangePasswordForm, RegisterForm
from wtforms import StringField


class ExtendedRegisterForm(RegisterForm):
    name = StringField("Full Name")


# The library verifies the current password asynchronously, including OAuth users.
OAuthAwareChangePasswordForm = ChangePasswordForm
