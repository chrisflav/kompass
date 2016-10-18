from django.db import models


class Group(models.Model):
    name = models.CharField(max_length=20)  # name of group e.g: J1 etc.
    min_age = models.IntegerField(default=5)  # in years

    def __str__(self):
        return "Group {0}".format(self.name)


class Member(models.Model):
    prename = models.CharField(max_length=20)
    lastname = models.CharField(max_length=20)
    email = models.EmailField(max_length=100, default="")
    birth_date = models.DateField('birth date')  # to determine the age
    group = models.ManyToManyField(Group)

    def __repr__(self):
        return self.name

    @property
    def name(self):
        """Returning whole name (prename + lastname)"""
        return "{0} {1}".format(self.prename, self.lastname)
