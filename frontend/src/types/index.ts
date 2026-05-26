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
  box_size: number | null;
  box_label: string;
  currency: string;
  url?: string;
  points: HistoryPoint[];
  current_price?: number | null;
  min_price?: number | null;
  max_price?: number | null;
  record_count?: number;
}

export interface PriceHistoryResponse {
  cigar_id: number;
  cigar_name: string;
  cigar_name_en?: string;
  cigar_brand?: string;
  cigar_brand_cn?: string;
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
