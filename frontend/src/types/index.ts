export interface Source {
  id: number;
  name: string;
  slug: string;
  url?: string;
}

export interface PriceSnapshot {
  id: number;
  cigar: number;
  cigar_name: string;
  cigar_english_name?: string;
  cigar_brand: string;
  cigar_brand_cn?: string;
  cigar_image_url?: string;
  scraped_name?: string;
  source: number;
  source_name: string;
  source_slug: string;
  price: number;
  currency: string;
  box_size: number | null;
  in_stock: boolean;
  url?: string;
  snapshot_date: string;
  min_price?: number | null;
  max_price?: number | null;
  record_count?: number;
}

export interface HistoryPoint {
  date: string;
  price: number;
  in_stock: boolean;
}

export interface Variant {
  source_slug: string;
  source_name: string;
  scraped_name?: string;
  box_size: number | null;
  box_label: string;
  currency: string;
  url?: string;
  points: HistoryPoint[];
  current_price?: number | null;
  current_price_cny?: number | null;
  price_per_stick?: number | null;
  min_price?: number | null;
  max_price?: number | null;
  record_count?: number;
  in_stock?: boolean;
  delisted?: boolean;
  scraped_at?: string;
}

export interface PriceHistoryResponse {
  cigar_id: number;
  cigar_name: string;
  cigar_name_en?: string;
  cigar_brand?: string;
  cigar_brand_cn?: string;
  release_type_cn?: string;
  variants: Variant[];
}

export interface CigarGroup {
  cigar_id: number;
  brand: string;
  brand_en?: string;
  brand_cn?: string;
  name: string;
  name_en?: string;
  image_url?: string;
  prices: PriceSnapshot[];
}

export interface BrandInfo {
  name: string;
  nameEn?: string;
  logoUrl: string;
}

export interface CigarListItem {
  cigar_id: number;
  cigar_name: string;
  cigar_name_en: string;
  cigar_brand: string;
  cigar_brand_cn: string;
  cigar_image_url: string;
  release_type_cn?: string;
  sources: {
    source_id: number;
    source_name: string;
    source_slug: string;
    price: number;
    price_cny: number | null;
    currency: string;
    box_size: number | null;
    in_stock: boolean;
    url: string;
  }[];
  in_stock: boolean;
  avg_per_stick_cny: number | null;
}

export interface AggregatedSourceEntry {
  source_id: number;
  source_name: string;
  source_slug: string;
  price: number | null;
  currency: string;
  price_cny: number | null;
  box_size: number | null;
  box_price: number | null;
  in_stock: boolean;
  scraped_at: string | null;
  url: string | null;
  change_pct?: number | null;
  change_direction?: string | null;
}

export interface AggregatedCigar {
  cigar_id: number;
  cigar_name: string;
  cigar_english_name: string | null;
  cigar_brand: string;
  cigar_brand_cn: string | null;
  sources: AggregatedSourceEntry[];
  any_in_stock: boolean;
  best_price: number | null;
  best_price_source: string | null;
  change_pct?: number | null;
  change_direction?: string | null;
}

export interface AlertItem {
  id: number;
  cigar: number;
  cigar_name: string;
  source: number;
  source_name: string;
  condition: string;
  condition_label: string;
  target_price: number;
  enabled: boolean;
  last_triggered?: string;
}
