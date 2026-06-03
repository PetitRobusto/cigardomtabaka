export interface Source {
  id: number;
  name: string;
  slug: string;
  short_name?: string;
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
  source_short_name?: string;
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
  original_price: number | null;
  price_cny: number | null;
  in_stock: boolean;
}

export interface Variant {
  source_slug: string;
  source_name: string;
  source_short_name?: string;
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
  scraped_at?: string;
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

export interface CigarListItem {
  cigar_id: number;
  cigar_name: string;
  cigar_name_en: string;
  cigar_brand: string;
  cigar_brand_cn: string;
  cigar_image_url: string;
  sources: {
    source_id: number;
    source_name: string;
    source_short_name?: string;
    source_slug: string;
    price: number;
    original_price: number | null;
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
  original_price: number | null;
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

// =================== NEW CATALOG TYPES ===================

export interface BrandItem {
  english_name: string;
  name: string;
  slug: string;
  logo_url: string | null;
  origin: string;
  category: string;
  cigar_count: number;
}

export interface BrandSection {
  key: string;
  label: string;
  brands: BrandItem[];
}

export interface BrandListResponse {
  sections: BrandSection[];
  total_brands: number;
}

export interface CigarChild {
  id: number;
  name: string;
  english_name: string;
  release_type: string;
  release_type_cn: string;
}

export interface CigarSummary {
  id: number;
  name: string;
  english_name: string;
  vitola: string;
  vitola_cn: string;
  length: number | null;
  ring_gauge: number | null;
  release_type: string;
  release_type_cn: string;
  status: string;
  thumb_url: string | null;
  image_url: string | null;
  children: CigarChild[];
}

export interface CigarSection {
  label: string;
  is_header?: boolean;
  cigars: CigarSummary[];
}

export interface BrandDetailResponse {
  brand: {
    english_name: string;
    name: string;
    slug: string;
    logo_url: string | null;
    origin: string;
    category: string;
    is_discontinued: boolean;
  };
  sections: CigarSection[];
  total: number;
}

export interface CigarImage {
  url: string;
  thumbnail_url: string | null;
  image_type: string;
  order: number;
  is_primary: boolean;
}

export interface CigarDetailResponse {
  cigar: {
    id: number;
    brand: string;
    english_name: string;
    name: string;
    vitola: string;
    vitola_cn: string;
    length: number | null;
    ring_gauge: number | null;
    common_name: string;
    common_name_cn: string;
    origin: string;
    status: string;
    release_type: string;
    release_type_cn: string;
    release_name: string;
    production_method: string;
    packagings: string[];
  };
  brand: {
    english_name: string;
    name: string;
    slug: string;
    logo_url: string | null;
    cigar_count: number;
  } | null;
  images_by_type: Record<string, CigarImage[]>;
  total_images: number;
  related: {
    id: number;
    name: string;
    english_name: string;
    vitola: string;
    release_type_cn: string;
    thumb_url: string | null;
  }[];
  children: {
    id: number;
    name: string;
    english_name: string;
    release_type: string;
    release_type_cn: string;
    thumb_url: string | null;
  }[];
}

export interface InventoryItem {
  id: number;
  brand: string;
  name: string;
  english_name: string;
  release_type_cn: string | null;
  release_type: string | null;
  total_stock: number;
  total_cost: number;
  avg_cost: number;
  latest_date: string | null;
}

export interface InventoryResponse {
  cigars: InventoryItem[];
  brands: string[];
  stats: {
    brand_count: number;
    cigar_count: number;
    total_qty: number;
    total_cost: number;
  };
}

export interface PrivnoteResponse {
  title: string;
  note_type?: string;
  data?: InventoryViewData | PaymentData | MessageData;
  has_password?: boolean;
  requires_password?: boolean;
  burn_after_read?: boolean;
  is_destroyed?: boolean;
  expires_at?: string;
  url?: string;
  token?: string;
  error?: string;
  reason?: string;
  sales_order_id?: number | null;
}

// =================== PRIVNOTE UPGRADE TYPES ===================

export interface PaymentMethod {
  id: number;
  method_type: 'bank_card' | 'wechat' | 'alipay';
  label: string;
  bank_name?: string;
  card_number?: string;
  card_holder?: string;
  qr_url?: string | null;
}

export interface SearchCigarResult {
  id: number;
  name: string;
  english_name: string;
  brand: string;
  vitola: string;
  thumb_url: string | null;
  stock_qty: number;
  batches: {
    batch_id: number;
    box_size: number;
    remaining: number;
    unit_cost_cny: number;
  }[];
}

export interface PaymentItem {
  cigar_id: number;
  batch_id?: number;
  name: string;
  english_name: string;
  vitola: string;
  thumb_url: string | null;
  quantity: number;
  unit_price: number;
  box_size: number;
}

export interface PaymentData {
  mode: 'payment';
  items: {
    name: string;
    english_name: string;
    vitola: string;
    quantity: number;
    unit_price: number;
    subtotal: number;
    thumb_url: string;
  }[];
  total: number;
  extra_fees: { name: string; amount: number }[];
  extra_total: number;
  grand_total: number;
  payment_methods: PaymentMethod[];
  customer_name: string;
  remark: string;
}

export interface MessageData {
  mode: 'message';
  text: string;
  attachments: { name: string; url: string }[];
}

export interface CustomerResult {
  id: number;
  name: string;
  phone: string;
}

export interface ExtraFee {
  name: string;
  amount: number;
}

export interface InventoryViewData {
  mode: 'inventory';
  brand_groups: {
    brand: string;
    name: string;
    logo_url: string | null;
    items: {
      name: string;
      english_name: string;
      vitola: string;
      box_size: number;
      full_boxes: number;
      loose: number;
      total_sticks: number;
      box_price: number;
      stick_price: number;
      thumb_url: string;
    }[];
  }[];
  total_items: number;
  total_boxes: number;
  total_loose: number;
  empty: boolean;
}
