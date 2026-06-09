from django.core.management.base import BaseCommand
from cigars.models import CigarPrice


class Command(BaseCommand):
    help = '将所有现有 CigarPrice 记录的 can_preorder 设为 True'

    def handle(self, *args, **options):
        updated = CigarPrice.objects.all().update(can_preorder=True)
        self.stdout.write(self.style.SUCCESS(f'已将 {updated} 条 CigarPrice 记录的 can_preorder 设为 True'))
