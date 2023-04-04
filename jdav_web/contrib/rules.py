from django.contrib.auth import get_permission_codename
import rules.contrib.admin
import rules

def memberize_user(func):
    def inner(user, other):
        if not hasattr(user, 'member'):
            return False
        return func(user.member, other)
    return inner


def has_global_perm(name):
    @rules.predicate
    def pred(user, obj):
        return user.has_perm(name)

    return pred
