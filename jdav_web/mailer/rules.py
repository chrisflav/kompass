from contrib.rules import memberize_user
from rules import predicate

@predicate
@memberize_user
def is_creator(self, message):
    if message is None:
        return False

    return message.created_by == self
