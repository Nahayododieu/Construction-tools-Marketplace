from .models import Category


def navigation(request):
    return {
        'navigation_categories': Category.objects.order_by('name')[:8]
    }
