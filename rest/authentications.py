from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from allauth.socialaccount.models import SocialToken
from django.utils import timezone

class SocialTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return None

        try:
            token_type, token = auth_header.split()
            if token_type.lower() != 'bearer':
                raise AuthenticationFailed("Invalid token type")

            """
            Bring the social token information in the database
            """
            social_token = SocialToken.objects.get(token=token)
            
            if social_token.expires_at and social_token.expires_at < timezone.now():
                raise AuthenticationFailed("Token has expired")

            # You can retrieve the user from the SocialToken's account
            user = social_token.account.user

            return (user, None)
        
        except SocialToken.DoesNotExist:
            raise AuthenticationFailed("Invalid token")

        except ValueError:
            raise AuthenticationFailed("Invalid Authorization header format")