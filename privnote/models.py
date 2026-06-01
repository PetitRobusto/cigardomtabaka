from django.db import models
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.hashers import make_password, check_password


class Privnote(models.Model):
    """一次性客户文档 — 库存展示 / 销售单据"""

    class NoteType(models.TextChoices):
        CATALOG = 'catalog', '库存展示'
        SALES = 'sales', '销售单据'

    token = models.CharField(max_length=12, unique=True, db_index=True)
    note_type = models.CharField('类型', max_length=10, choices=NoteType.choices, default='catalog')
    title = models.CharField('标题', max_length=200, default='Untitled')

    brand = models.ForeignKey(
        'cigars.Brand', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='privnotes'
    )

    html = models.TextField('预渲染HTML', blank=True)
    data_json = models.JSONField('结构化数据', default=dict, blank=True)

    # 安全配置
    has_password = models.BooleanField('密码保护', default=False)
    password_hash = models.CharField('密码哈希', max_length=128, blank=True)
    burn_after_read = models.BooleanField('阅后即焚', default=True)
    max_views = models.IntegerField('最大查看次数', default=1)

    # 状态
    view_count = models.IntegerField('已查看次数', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    expires_at = models.DateTimeField('过期时间')

    created_by = models.ForeignKey(
        'cigars.User', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='创建人'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Privnote'
        verbose_name_plural = 'Privnote'

    def __str__(self):
        return f'{self.get_note_type_display()} · {self.title}'

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_destroyed(self):
        if not self.burn_after_read and self.max_views == 0:
            return False
        return self.view_count >= self.max_views

    @property
    def is_accessible(self):
        return not self.is_expired and not self.is_destroyed

    def set_password(self, raw_password):
        self.password_hash = make_password(raw_password)
        self.has_password = True

    def verify_password(self, raw_password):
        return check_password(raw_password, self.password_hash)

    def mark_viewed(self):
        self.view_count += 1
        self.save(update_fields=['view_count'])

    @classmethod
    def create(cls, **kwargs):
        import uuid
        kwargs.setdefault('token', uuid.uuid4().hex[:12])
        kwargs.setdefault('expires_at', timezone.now() + timedelta(hours=24))
        kwargs.setdefault('burn_after_read', True)
        kwargs.setdefault('max_views', 1)
        return cls.objects.create(**kwargs)
