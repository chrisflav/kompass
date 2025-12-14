from django.apps import AppConfig


class TestDataConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "test_data"
    verbose_name = "Test Data"
