from django.contrib import admin
from django.db.models import Count

from .models import Option, Poll


class OptionInline(admin.TabularInline):
    model = Option
    extra = 0
    max_num = 5


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    list_display = ("question", "author", "created_at", "vote_total")
    search_fields = ("question", "author__username")
    list_select_related = ("author",)
    inlines = [OptionInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_vote_total=Count("votes"))

    @admin.display(description="Oy sayısı", ordering="_vote_total")
    def vote_total(self, obj):
        return obj._vote_total
