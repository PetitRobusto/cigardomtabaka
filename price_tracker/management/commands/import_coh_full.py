#!/usr/bin/env python3
"""Import COH price data scraped from browser into PriceSnapshot table."""
import json, sys, os, re
from pathlib import Path

# Django setup
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cigardomtabaka.settings')
import django
django.setup()

from price_tracker.models import PriceSource, PriceSnapshot
from price_tracker.scraper import match_cigar_by_name
from cigars.models import Cigar
from django.utils import timezone

COH_SLUG_BRAND_MAP = {
    'belinda': 'Belinda', 'bolivar': 'Bolívar', 'cohiba': 'Cohiba',
    'combinaciones': 'Combinaciones', 'cuaba': 'Cuaba',
    'diplomaticos': 'Diplomáticos', 'el-rey-del-mundo': 'El Rey del Mundo',
    'fonseca': 'Fonseca', 'guantanamera': 'Guantanamera',
    'h.upmann': 'H. Upmann', 'hoyo-de-monterrey': 'Hoyo de Monterrey',
    'jose-l.-piedra': 'José L. Piedra', 'juan-lopez': 'Juan López',
    'la-flor-de-cano': 'La Flor de Cano', 'la-gloria-cubana': 'La Gloria Cubana',
    'montecristo': 'Montecristo', 'partagas': 'Partagás',
    'por-larranaga': 'Por Larrañaga', 'punch': 'Punch',
    'quai-dorsay': "Quai d'Orsay", 'quintero-y-hermano': 'Quintero',
    'rafael-gonzalez': 'Rafael González', 'ramon-allones': 'Ramón Allones',
    'romeo-y-julieta': 'Romeo y Julieta', 'saint-luis-rey': 'Saint Luis Rey',
    'san-cristobal-de-la-habana': 'San Cristóbal', 'sancho-panza': 'Sancho Panza',
    'trinidad': 'Trinidad', 'troya': 'Troya',
    'vegas-robaina': 'Vegas Robaina', 'vegueros': 'Vegueros', 'vintage': 'Vintage',
}

def clean_cigar_name(name):
    """Clean COH product name for matching."""
    name = name.strip()
    # Remove year suffixes like " - 2016", " -  2010"
    name = re.sub(r'\s*[-–]\s*\d{4}\s*$', '', name)
    # Remove "5 Pack- ", "5 Packs- " prefix
    name = re.sub(r'^\d+\s*Packs?-\s*', '', name)
    # Remove pack suffixes
    name = re.sub(r'\s+(C/P|A/T|LCDH|EL\s+\d{4}|RE\s+\w+(\s+\d{4})?)\s*$', '', name)
    return name.strip()

def main(json_file):
    with open(json_file) as f:
        data = json.load(f)
    
    source = PriceSource.objects.get(slug='coh')
    now = timezone.now()
    
    stats = {'total': 0, 'matched': 0, 'created': 0, 'skipped': 0}
    
    for slug, products in data.items():
        brand = COH_SLUG_BRAND_MAP.get(slug, slug.replace('-', ' ').title())
        
        for prod in products:
            stats['total'] += 1
            name = clean_cigar_name(prod['name'])
            price = prod.get('price')
            
            if not price:
                stats['skipped'] += 1
                continue
            
            # Try to match
            cigar = match_cigar_by_name(name, brand_hint=brand)
            
            if not cigar:
                # Try harder - remove common noise
                name2 = re.sub(r'\s*(Travel Humidor|Gift Box|Humidor|Limited Edition|Year of the \w+|Anejados)\s*', '', name, flags=re.I).strip()
                if name2 != name:
                    cigar = match_cigar_by_name(name2, brand_hint=brand)
            
            if cigar:
                stats['matched'] += 1
                # Check if we already have a snapshot for this cigar+source today
                existing = PriceSnapshot.objects.filter(
                    cigar=cigar, source=source,
                    scraped_at__date=now.date()
                ).first()
                
                if not existing:
                    PriceSnapshot.objects.create(
                        cigar=cigar,
                        source=source,
                        price=price,
                        currency='USD',
                        price_cny=round(price * 7.25, 2),
                        in_stock=True,
                        scraped_at=now,
                    )
                    stats['created'] += 1
            else:
                # Print unmatched for debugging
                if stats['total'] <= 10 or stats['total'] % 50 == 0:
                    print(f"  UNMATCHED: [{brand}] {name} (raw: {prod['name']})")
    
    print(f"\n=== Import Summary ===")
    print(f"Total products: {stats['total']}")
    print(f"Matched to DB: {stats['matched']}")
    print(f"New snapshots: {stats['created']}")
    print(f"Skipped (no price): {stats['skipped']}")
    print(f"Match rate: {stats['matched']}/{stats['total']} = {stats['matched']/stats['total']*100:.1f}%")
    
    return stats

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <coh_data.json>")
        sys.exit(1)
    main(sys.argv[1])
