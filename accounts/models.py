from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, username, password, **extra_fields):
        if not email:
            raise ValueError("E-posta zorunludur.")
        if not username:
            raise ValueError("Kullanıcı adı zorunludur.")
        user = self.model(
            email=self.normalize_email(email).lower(),
            username=username.lower(),
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, username, password, **extra_fields)

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields["is_staff"] is not True or extra_fields["is_superuser"] is not True:
            raise ValueError("Süper kullanıcı is_staff ve is_superuser olmalıdır.")
        return self._create_user(email, username, password, **extra_fields)


class User(AbstractUser):
    """E-posta ile giriş yapılan kullanıcı. E-posta ve kullanıcı adı küçük harfle saklanır."""

    first_name = None
    last_name = None

    email = models.EmailField("e-posta", unique=True)
    username = models.CharField("kullanıcı adı", max_length=20, unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="user_email_ci_unique"),
            models.UniqueConstraint(Lower("username"), name="user_username_ci_unique"),
        ]

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        self.username = self.username.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username
