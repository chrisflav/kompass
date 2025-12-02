from django.contrib.auth.models import User
from rest_framework import serializers, status
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mailer.models import EmailAddress
from members.models import Member


class EmailForwardSerializer(serializers.Serializer):
    """Serializer for email forwarding request"""
    email = serializers.EmailField(required=True)


class EmailForwardResponseSerializer(serializers.Serializer):
    """Serializer for email forwarding response"""
    forward_to = serializers.ListField(child=serializers.EmailField())


@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def email_forward_lookup(request):
    """
    API endpoint to lookup email forwarding addresses.

    Given an email address (username@domain.com), returns a list of email addresses
    that the incoming mail should be forwarded to based on two rules:

    1. If username matches a logindata user's username, forward to the associated member's email
    2. If username matches an EmailAddress, forward to all members and members in groups
       specified in the to_members and to_groups fields

    Request body:
        {
            "email": "username@domain.com"
        }

    Response:
        {
            "forward_to": ["email1@example.com", "email2@example.com"]
        }
    """
    serializer = EmailForwardSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data['email']
    # Extract username from email (part before @)
    username = email.split('@')[0]

    forward_addresses = set()

    # Rule 1: Check if username matches a User
    try:
        user = User.objects.get(username=username)
        # Get the associated member
        if hasattr(user, 'member'):
            member = user.member
            if member.email:
                forward_addresses.add(member.email)
    except User.DoesNotExist:
        pass

    # Rule 2: Check if username matches an EmailAddress
    try:
        email_address = EmailAddress.objects.get(name=username)
        # Get all members from to_members
        for member in email_address.to_members.all():
            if member.email:
                forward_addresses.add(member.email)

        # Get all members from groups in to_groups
        for group in email_address.to_groups.all():
            for member in group.member_set.all():
                if member.email:
                    forward_addresses.add(member.email)
    except EmailAddress.DoesNotExist:
        pass

    # Convert set to sorted list for consistent output
    response_data = {
        'forward_to': sorted(list(forward_addresses))
    }

    return Response(response_data, status=status.HTTP_200_OK)
