from django.db import models


class RateLimitHit(models.Model):
    """Hız sınırı için tek bir istek kaydı. `key` ham IP değil, tuzlu özetidir."""

    scope = models.CharField(max_length=20)
    key = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["scope", "key", "created_at"], name="throttle_lookup_idx"),
            models.Index(fields=["created_at"], name="throttle_created_idx"),
        ]

    def __str__(self):
        return f"{self.scope} {self.key[:8]}"
