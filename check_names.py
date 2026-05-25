import os, sys
sys.path.insert(0, os.path.expanduser('~/moscow_cigar'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'moscow_cigar_backend.settings')
import django; django.setup()
from cigars.models import Cigar

print('=== Cohiba Siglo & BHK ===')
for c in Cigar.objects.filter(brand='Cohiba').order_by('english_name'):
    if c.name and ('Siglo' in c.english_name or 'BHK' in c.english_name):
        print(f'  {c.english_name:25s} -> {c.name}')

print()
print('=== Montecristo No.1-5 ===')
for c in Cigar.objects.filter(brand='Montecristo', english_name__startswith='Montecristo No.').order_by('english_name'):
    if c.name: print(f'  {c.english_name:25s} -> {c.name}')

print()
print('=== Partagas Serie D ===')
for c in Cigar.objects.filter(brand='Partagás', english_name__contains='Serie D').order_by('english_name')[:4]:
    if c.name: print(f'  {c.english_name:25s} -> {c.name}')

named = Cigar.objects.exclude(name='').count()
print(f'\nTotal: {named}/1178 ({named*100//1178}%)')
