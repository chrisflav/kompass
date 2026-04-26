from rest_framework import serializers

from .models import Freizeit


class FreizeitSerializer(serializers.ModelSerializer):
    """Serializer for the `Freizeit` model."""

    class Meta:
        model = Freizeit
        fields = [
            "id",
            "pk",
            "duration",
            "jugendleiter",
            "kilometers_traveled",
            "get_tour_approach",
            "night_count",
        ]
        read_only_fields = ["duration"]
        depth = 10
