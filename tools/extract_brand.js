/**
 * Universal cigar brand page extractor.
 * Handles Current, Discontinued, AND Special Releases with multi-cigar humidors.
 * 
 * Ring gauge extraction:
 *   - Current/Discontinued: span[itemprop="value"] inside .cigarDetailsSize
 *   - Special Releases: a[href*="ringlow"] link text
 * Length: a[href*="lengthmm"] link text (works for all)
 */
() => {
  const BASE = 'https://www.cubancigarwebsite.com';
  const BRAND_SLUG = '__BRAND_SLUG__';
  const BRAND_NAME = '__BRAND_NAME__';

  const maintable = document.querySelector('.maintable');
  if (!maintable) return JSON.stringify({ error: 'No .maintable found', brand: BRAND_NAME, results: [] });

  const children = Array.from(maintable.children);
  let currentSection = 'Current';
  const results = [];

  for (const row of children) {
    const cls = row.className || '';

    // --- Section detection ---
    if (cls.includes('section-head')) {
      const t = row.textContent.trim();
      if (/Current\s*Production/i.test(t)) currentSection = 'Current';
      else if (/Discontinued\s*Production/i.test(t)) currentSection = 'Discontinued';
      else if (/Special\s*Releases/i.test(t)) currentSection = 'Special Releases';
      continue;
    }

    // Skip decorative rows (text-center without section-head)
    if (cls.includes('text-center')) continue;

    // Must be a real entry
    if (!cls.includes('entry')) continue;

    // --- Get all cigarDetailsHead blocks ---
    const detailsHeads = row.querySelectorAll('.cigarDetailsHead');
    if (detailsHeads.length === 0) continue;

    const isSpecial = currentSection === 'Special Releases';

    // --- Release-level info (for Special Releases) ---
    let releaseName = '';
    let releaseUrl = '';
    let releaseType = '';

    if (isSpecial) {
      const rnEl = row.querySelector('.cigarReleaseName a');
      releaseName = rnEl ? rnEl.textContent.trim() : '';
      releaseUrl = rnEl ? (rnEl.getAttribute('href') || '') : '';
      const rtEl = row.querySelector('.srsub a');
      releaseType = rtEl ? rtEl.textContent.trim() : '';
    }

    // --- Extract sub-cigars from cigarDetailsHead blocks ---
    const subCigars = [];
    for (const dh of detailsHeads) {
      // Name
      const nameEl = dh.querySelector('.cigarDetailsName a');
      let cigarName = nameEl ? nameEl.textContent.trim() : '';

      // Extract quantity from parentheses like "(10)"
      let quantity = null;
      const qtyMatch = cigarName.match(/\((\d+)\)/);
      if (qtyMatch) {
        quantity = parseInt(qtyMatch[1]);
        cigarName = cigarName.replace(/\s*\(\d+\)\s*/, '').trim();
      }
      cigarName = cigarName.replace(/\s+/g, ' ').trim();

      // Vitola (factory name)
      const factoryEl = dh.querySelector('.cigarDetailsFactoryName a');
      const vitola = factoryEl ? factoryEl.textContent.trim() : '';

      // Ring gauge: try link first (Special), then span[itemprop="value"] (Current/Discontinued)
      let ring = null;
      const ringLink = dh.querySelector('a[href*="ringlow"]');
      if (ringLink) {
        ring = parseFloat(ringLink.textContent.trim());
      } else {
        const sizeDiv = dh.querySelector('.cigarDetailsSize');
        if (sizeDiv) {
          const valueSpans = sizeDiv.querySelectorAll('span[itemprop="value"]');
          if (valueSpans.length > 0) {
            ring = parseFloat(valueSpans[0].textContent.trim());
          }
        }
      }

      // Length: always from link
      let length = null;
      const lengthLink = dh.querySelector('a[href*="lengthmm"]');
      if (lengthLink) {
        length = parseFloat(lengthLink.textContent.trim());
      }

      // Common name
      const cnEl = dh.querySelector('a[href*="commonnames"]');
      const commonName = cnEl ? cnEl.textContent.trim() : '';

      subCigars.push({
        name: cigarName,
        vitola: vitola,
        ring_gauge: ring,
        length_mm: length,
        common_name: commonName,
        quantity: quantity
      });
    }

    // --- Packaging text ---
    let packagingRaw = '';
    const ft = row.textContent;
    const pm = ft.match(/Packaging:\s*([\s\S]*?)(?=Status:|Construction:|Bands:|Ring|$)/i);
    packagingRaw = pm ? pm[1].replace(/\s+/g, ' ').trim().substring(0, 500) : '';

    // --- Status text ---
    const sm = ft.match(/Status:\s*([^\n]+)/);
    const statusText = sm ? sm[1].trim() : '';

    // --- Box sizes from packaging ---
    const bsSet = new Set();
    const re = /(?:box|pack|jar|humidor)\s+(?:of\s+)?(\d+)/gi;
    let m;
    while ((m = re.exec(packagingRaw)) !== null) {
      const s = parseInt(m[1]);
      if (s <= 100) bsSet.add(s);
    }
    const boxSizes = Array.from(bsSet).sort((a, b) => a - b);

    // --- Name cleaning for Special Releases ---
    // Split concatenated names like "PirámidesEdición Limitada"
    let cleanReleaseName = releaseName;
    let cleanReleaseType = releaseType;

    if (isSpecial && releaseName) {
      // Try to split at known keywords
      const keywords = [
        'Edición Limitada', 'Edición Regional', 'Edicion Limitada', 'Edicion Regional',
        'La Casa del Habano', 'Reserva del Milenio', 'Reserva Cosecha',
        'Gran Reserva', 'Colección Habanos', 'Coleccion Habanos',
        'Travel Humidor', 'Diplomatic Gifts', 'VIP Gifts',
        'Aniversario Humidor', 'Aniversario Jar',
        'Tributo', 'Réplica de Humidor', 'Replica de Humidor',
        'Habanos Añejados', 'Habanos Añejados',
        'Serie A Humidor', 'Serie', 'Selección',
        'Especialista en Habanos', 'LCDH', 'Exclusive',
        'Año Chino', '520 Aniversario',
        'Humidor Cohiba', 'Grand Churchills',
        'Salomones Espanola', 'S. T. Dupont',
        'Jarra', 'Siglo de Oro',
        'Limited Edition', 'Regional Edition',
        'Special Events', 'Special Release',
        'Commemorative Release', 'Millennium Reserve',
        'Grand Reserve', 'Reserve Series',
        'Habanos Collection', 'Chinese Year',
        'Duty Free', 'Habanos Specialist'
      ];

      for (const kw of keywords) {
        const idx = releaseName.toLowerCase().indexOf(kw.toLowerCase());
        if (idx > 0 && (releaseName[idx - 1] === ' ' || /[A-Z]/.test(releaseName[idx - 1]))) {
          cleanReleaseName = releaseName.substring(0, idx).trim();
          if (!cleanReleaseType || cleanReleaseType.length < 3) {
            cleanReleaseType = releaseName.substring(idx).trim();
          }
          break;
        }
      }
    }

    // --- Build output records ---
    for (const sc of subCigars) {
      const record = {
        brand: BRAND_NAME,
        name: sc.name || (isSpecial ? cleanReleaseName : ''),
        common_name: sc.common_name,
        vitola: sc.vitola,
        ring_gauge: sc.ring_gauge,
        length_mm: sc.length_mm,
        status: isSpecial ? 'Special Releases' : currentSection,
        release_type: isSpecial ? cleanReleaseType : '',
        release_name: isSpecial ? cleanReleaseName : '',
        url: releaseUrl ? BASE + releaseUrl : '',
        packaging_raw: packagingRaw,
        box_sizes: boxSizes,
        sub_quantity: sc.quantity,
        status_text: statusText
      };

      results.push(record);
    }
  }

  return JSON.stringify({
    brand: BRAND_NAME,
    total: results.length,
    current_count: results.filter(r => r.status === 'Current').length,
    discontinued_count: results.filter(r => r.status === 'Discontinued').length,
    special_count: results.filter(r => r.status === 'Special Releases').length,
    with_ring: results.filter(r => r.ring_gauge !== null).length,
    with_length: results.filter(r => r.length_mm !== null).length,
    with_both: results.filter(r => r.ring_gauge !== null && r.length_mm !== null).length,
    missing_both: results.filter(r => r.ring_gauge === null || r.length_mm === null).length,
    results: results
  });
}
