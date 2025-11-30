import rules.contrib.admin


def memberize_user(func):
    def inner(user, other):
        if not hasattr(user, "member"):
            return False
        return func(user.member, other)

    return inner


def has_global_perm(name):
    @rules.predicate
    def pred(user, obj):
        return user.has_perm(name)

    return pred
