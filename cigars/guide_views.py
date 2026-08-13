"""业务引导状态和操作 API。"""
from functools import wraps

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import GuideConfiguration, UserGuideProgress


def _staff_only(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'ok': False, 'error': 'Authentication required'}, status=401)
        if not request.user.is_staff:
            return JsonResponse({'ok': False, 'error': 'Forbidden'}, status=403)
        return view(request, *args, **kwargs)
    return wrapped


def _summary(user):
    config, _ = GuideConfiguration.objects.get_or_create(pk=1)
    progress, _ = UserGuideProgress.objects.get_or_create(user=user)
    return {
        'version': config.version,
        'auto_show_enabled': config.auto_show_enabled,
        'should_show': config.auto_show_enabled and (
            progress.completed_version < config.version or progress.force_show_next_time
        ),
        'completed_version': progress.completed_version,
        'force_show_next_time': progress.force_show_next_time,
    }


@require_GET
@_staff_only
def guide_status(request):
    return JsonResponse(_summary(request.user))


@require_POST
@_staff_only
def guide_complete(request):
    config, _ = GuideConfiguration.objects.get_or_create(pk=1)
    progress, _ = UserGuideProgress.objects.get_or_create(user=request.user)
    if progress.completed_version < config.version:
        progress.completed_version = config.version
        progress.completed_at = timezone.now()
    elif progress.completed_at is None:
        progress.completed_at = timezone.now()
    progress.force_show_next_time = False
    progress.save(update_fields=['completed_version', 'completed_at', 'force_show_next_time'])
    return JsonResponse({'completed': True, **_summary(request.user)})


@require_POST
@_staff_only
def guide_replay(request):
    progress, _ = UserGuideProgress.objects.get_or_create(user=request.user)
    progress.force_show_next_time = True
    progress.save(update_fields=['force_show_next_time'])
    return JsonResponse({'replayed': True, **_summary(request.user)})
