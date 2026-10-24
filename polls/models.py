from django.conf import settings
from django.core.validators import MaxValueValidator, MinLengthValidator
from django.db import models
from django.db.models import Count, Prefetch
from django.urls import reverse

MIN_OPTIONS = 2
MAX_OPTIONS = 5


class PollQuerySet(models.QuerySet):
    def with_results(self):
        """Yazar ve vote_count ile işaretlenmiş seçenekleri sabit sayıda sorguyla getirir."""
        options = Option.objects.annotate(vote_count=Count("votes")).order_by("position")
        return self.select_related("author").prefetch_related(Prefetch("options", queryset=options))


class Poll(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="polls"
    )
    question = models.CharField("soru", max_length=140, validators=[MinLengthValidator(5)])
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    closed_at = models.DateTimeField("kapanış zamanı", null=True, blank=True, db_index=True)

    objects = PollQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        self.question = " ".join(self.question.split())
        super().save(*args, **kwargs)

    @property
    def is_closed(self):
        return self.closed_at is not None

    def get_absolute_url(self):
        return reverse("poll_detail", args=[self.pk])

    def __str__(self):
        return self.question


class Option(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="options")
    text = models.CharField("seçenek", max_length=60)
    position = models.PositiveSmallIntegerField(validators=[MaxValueValidator(MAX_OPTIONS - 1)])

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["poll", "position"], name="option_poll_position_unique"),
        ]

    def __str__(self):
        return self.text


class Vote(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="votes")
    option = models.ForeignKey(Option, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="votes"
    )
    voter_key = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["poll", "voter_key"], name="vote_poll_voter_unique"),
        ]

    def __str__(self):
        return f"{self.voter_key} → {self.option_id}"
