#!/usr/bin/env python3
"""Merge per-brand JSON files into cigars_catalog.json format."""
import json, os, re

SRC_DIR = os.path.expanduser("~/.hermes/cigar_inventory")
OLD_CATALOG = os.path.expanduser("~/moscow_cigar/cigars_catalog.json")
OUT = OLD_CATALOG  # overwrite

# New brands we crawled (slugs that exist as JSON files, excluding old brands)
NEW_BRANDS = {
    "cuaba": "Cuaba",
    "diplomaticos": "Diplomáticos",
    "el-rey-del-mundo": "El Rey del Mundo",
    "fonseca": "Fonseca",
    "jose-l-piedra": "José L. Piedra",
    "juan-lopez": "Juan López",
    "la-flor-de-cano": "La Flor de Cano",
    "la-gloria-cubana": "La Gloria Cubana",
    "por-larranaga": "Por Larrañaga",
    "quintero": "Quintero",
    "rafael-gonzalez": "Rafael González",
    "saint-luis-rey": "Saint Luis Rey",
    "san-cristobal": "San Cristóbal",
    "sancho-panza": "Sancho Panza",
    "vegas-robaina": "Vegas Robaina",
    "vegueros": "Vegueros",
}

def parse_packaging_raw(text):
    """Parse packagingRaw text into structured packagings JSON string.
    
    Example input: "Dress box of 25 cigars. Cardboard pack of 5 cigars (discontinued 2010)."
    Output: '[{"size": 25, "type": "Dress box", "discontinued": false}, ...]'
    """
    if not text:
        return "[]"
    
    packagings = []
    # Split by period followed by space and capital/number
    parts = re.split(r'\.\s+(?=[A-Z0-9])', text)
    
    for part in parts:
        part = part.strip().rstrip('.')
        if not part:
            continue
        
        # Extract size: "box/pack/jar/humidor of N" or "box/pack/jar/humidor N"
        size_match = re.search(r'(?:box|pack|jar|humidor|tin)\s+(?:of\s+)?(\d+)', part, re.I)
        size = int(size_match.group(1)) if size_match else None
        
        # Check discontinued
        discontinued = bool(re.search(r'discontinued', part, re.I))
        
        # Extract clean type name: remove "of N cigars" and parenthetical notes
        type_part = part
        # Remove "of N cigars" or "of N"
        type_part = re.sub(r'\s+of\s+\d+\s*(cigars?)?', '', type_part)
        # Remove parenthetical notes like "(released 2020, discontinued...)"
        type_part = re.sub(r'\([^)]*\)', '', type_part)
        # Remove trailing "in tissue", "in cellophane", "in aluminium foil", "in aluminium tubes"
        type_part = re.sub(r'\s+in\s+(tissue|cellophane|aluminium\s+(foil|tubes?)|gold\s+foil)(\s+and\s+individual\s+slide\s+lid\s+boxes?)?', '', type_part, flags=re.I)
        # Remove "with N cardboard packs"
        type_part = re.sub(r'\s+(in|with)\s+\d+\s+cardboard\s+packs?.*$', '', type_part, flags=re.I)
        # Remove "(discontinued XXXX)"
        type_part = re.sub(r'\s*\(.*$', '', type_part)
        # Clean up
        type_part = type_part.strip().rstrip('.').strip()
        
        if not type_part:
            type_part = "Unknown"
        
        # Only include if we got a valid size
        if size and size <= 100:
            packagings.append({
                "size": size,
                "type": type_part[:100],  # truncate long types
                "discontinued": discontinued
            })
    
    # Deduplicate (same size+type)
    seen = set()
    unique = []
    for p in packagings:
        key = (p["size"], p["type"])
        if key not in seen:
            seen.add(key)
            unique.append(p)
    
    return json.dumps(unique, ensure_ascii=False) if unique else "[]"


def normalize_product(p, brand_name):
    """Normalize a product dict to match old catalog format."""
    # Build packagings
    if "packagings" in p:
        # Already has structured packagings (e.g., cuaba.json)
        if isinstance(p["packagings"], str):
            packagings = p["packagings"]
        else:
            packagings = json.dumps(p["packagings"], ensure_ascii=False)
    else:
        packagings = parse_packaging_raw(p.get("packagingRaw", ""))
    
    # Determine release_type
    release_type = p.get("releaseType", "") or p.get("rt", "")
    
    return {
        "brand": brand_name,
        "name": p["name"],
        "vitola": p.get("vitola", "") or p.get("v", ""),
        "lengthMm": p.get("lengthMm") or p.get("ln"),
        "ringGauge": p.get("ringGauge") or p.get("rg"),
        "common_name": p.get("commonName", "") or p.get("cn", ""),
        "status": p.get("status", "Current"),
        "release_type": release_type,
        "url": p.get("url", ""),
        "packagings": packagings,
    }


def main():
    # Load old catalog
    with open(OLD_CATALOG) as f:
        old_catalog = json.load(f)
    print(f"Old catalog: {len(old_catalog)} products")
    
    old_brands = set(item["brand"] for item in old_catalog)
    
    # Process new brands
    new_products = []
    for slug, brand_name in NEW_BRANDS.items():
        filepath = os.path.join(SRC_DIR, f"{slug}.json")
        if not os.path.exists(filepath):
            print(f"  SKIP {brand_name}: file not found")
            continue
        
        with open(filepath) as f:
            data = json.load(f)
        
        for p in data:
            normalized = normalize_product(p, brand_name)
            new_products.append(normalized)
        
        print(f"  {brand_name}: {len(data)} products")
    
    print(f"\nNew products: {len(new_products)}")
    
    # Merge: keep old products that aren't in the new brand list
    merged = [item for item in old_catalog if item["brand"] not in NEW_BRANDS.values()]
    merged.extend(new_products)
    
    print(f"Merged: {len(merged)} total")
    
    # Write back
    with open(OUT, 'w') as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    
    print(f"Written to {OUT}")
    
    # Summary
    from collections import Counter
    counts = Counter(item["brand"] for item in merged)
    print("\n=== Brand counts ===")
    for brand, count in sorted(counts.items()):
        marker = " ★" if brand in NEW_BRANDS.values() else ""
        print(f"  {brand}: {count}{marker}")


if __name__ == "__main__":
    main()
