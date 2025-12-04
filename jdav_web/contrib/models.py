from django.db import models
from rules.contrib.models import RulesModelBase
from rules.contrib.models import RulesModelMixin
from django.contrib.admin.models import LogEntry, CHANGE
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model


# Create your models here.
class CommonModel(models.Model, RulesModelMixin, metaclass=RulesModelBase):
    class Meta:
        abstract = True
        default_permissions = (
            "add_global",
            "change_global",
            "view_global",
            "delete_global",
            "list_global",
            "view",
        )
        
    def log_admin_action(self, user, message, model_cls = None, action_flag=CHANGE):
        User = get_user_model()
        fallback_user = User.objects.filter(is_superuser=True).first()
        try:
            LogEntry.objects.log_action(
                user_id=user.pk if user else fallback_user.pk if fallback_user else 0,
                content_type_id=ContentType.objects.get_for_model(model_cls or self).pk,
                object_id=self.pk,
                object_repr=str(self),
                action_flag=action_flag,  
                change_message=message,
            )
        except Exception as e:
            # In case logging fails, we don't want to interrupt the main flow
            pass
