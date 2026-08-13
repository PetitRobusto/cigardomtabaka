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
  delisted?: boolean;
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
  data?: InventoryViewData | PaymentData | MessageData | QuoteData;
  has_password?: boolean;
  requires_password?: boolean;
  burn_after_read?: boolean;
  is_destroyed?: boolean;
  created_at?: string;
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
  remark?: string;
  fund_account_id?: number;
}

export interface SearchCigarResult {
  id: number;
  name: string;
  english_name: string;
  brand: string;
  brand_cn: string;
  vitola: string;
  length: number | null;
  ring_gauge: number | null;
  thumb_url: string | null;
  stock_qty: number;
  box_options: {
    box_size: number;
    available_boxes: number;
  }[];
  available_sticks: number;
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
  brand: string;
  brand_cn: string;
  vitola: string;
  length: number | null;
  ring_gauge: number | null;
  thumb_url: string | null;
  quantity: number;
  unit_price: number;
  box_size: number;
}

export interface RemarkImage {
  url: string;
  name: string;
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
  images?: RemarkImage[];
}

export interface MessageData {
  mode: 'message';
  text: string;
  attachments: { name: string; url: string }[];
  images?: RemarkImage[];
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

// =================== QUOTE TYPES ===================

export interface QuoteProduct {
  cigar_id: number;
  brand: string;
  brand_cn: string;
  name: string;
  english_name: string;
  vitola: string;
  box_size: number;
  wholesale_price: number;
  per_stick_price: number;
  thumb_url: string | null;
  in_stock: boolean;
  can_preorder: boolean;
}

export interface QuoteBrandGroup {
  brand: string;
  brand_cn: string;
  logo_url: string | null;
  items: QuoteProduct[];
}

export interface QuoteData {
  mode: 'quote';
  brand_groups: QuoteBrandGroup[];
  total_items: number;
  shipping_included: boolean;
  shipping_fee_per_stick?: number;
  customer_name?: string;
  custom_prices?: Record<number, number>;
}

export interface RecentPriceChange {
  cigar_id: number;
  cigar_name: string;
  cigar_brand: string;
  cigar_brand_cn: string;
  cigar_image_url: string;
  source_name: string;
  source_short_name: string;
  source_slug: string;
  box_size: number | null;
  old_price: number;
  new_price: number;
  old_price_cny: number | null;
  new_price_cny: number | null;
  currency: string;
  change_pct: number;
  change_direction: 'up' | 'down';
  changed_at: string;
}

export interface RecentRestock {
  cigar_id: number;
  cigar_name: string;
  cigar_brand: string;
  cigar_brand_cn: string;
  cigar_image_url: string;
  source_name: string;
  source_short_name: string;
  source_slug: string;
  box_size: number | null;
  price: number | null;
  price_cny: number | null;
  currency: string;
  restocked_at: string;
}

export interface RecentChangesResponse {
  price_changes: RecentPriceChange[];
  restocks: RecentRestock[];
}

// =================== SALES & ACCOUNTING WORKBENCH ===================

export interface PaymentOrderItem {
  cigar_name: string;
  quantity: number;
  sale_unit: 'stick' | 'box' | string;
  sale_quantity: number | null;
  unit_price: number;
}

export interface PaymentOrder {
  id: number;
  order_number: string;
  status: string;
  display_status: string;
  fulfillment_status: 'confirmed' | 'shipped' | string;
  payment_status: 'unpaid' | string;
  customer_name: string;
  customer?: { name: string } | null;
  amount_due_cny: number;
  items: PaymentOrderItem[];
}

export interface SalesOrderItem {
  id: number;
  cigar_id: number;
  cigar_name: string;
  quantity: number;
  sale_unit: 'stick' | 'box' | string;
  sale_quantity: number | null;
  box_size: number | null;
  unit_price: number;
  unit_cost: number;
  revenue: number;
  cost: number;
  profit: number;
  fulfillment_type: string;
  allocations: { id: number; batch_id: number; quantity: number; status: string; unit_cost_cny?: number | string; cost_cny?: number | string }[];
}

export interface SalesOrder {
  id: number;
  order_number: string;
  status: string;
  display_status: string;
  fulfillment_status: 'draft' | 'confirmed' | 'shipped' | 'cancelled' | string;
  payment_status: 'unpaid' | 'paid' | 'refund_pending' | 'refunded' | string;
  customer_id: number | null;
  customer_name: string;
  customer?: { id: number; name: string; phone: string } | null;
  goods_amount_cny: number;
  customer_transport_fee_cny: number;
  transport_payer: 'customer' | 'company';
  amount_due_cny: number;
  total_revenue: number;
  total_cost: number;
  total_profit: number;
  fifo_cost: number;
  contribution_profit: number;
  actual_transport_cost_cny: number;
  locked: boolean;
  created_at: string | null;
  confirmed_at: string | null;
  cancelled_at: string | null;
  note: string;
  items: SalesOrderItem[];
  sales_shipment: { id: number; business_date: string; fifo_cost_cny: number } | null;
  sales_receipt: { id: number; amount_cny: number; business_date: string; fund_account_id: number } | null;
  sales_refund: { id: number; amount_cny: number; business_date: string; fund_account_id: number } | null;
  sales_transport_cost: { id: number; actual_cost_cny: number; business_date: string; fund_account_id: number } | null;
  available_actions: string[];
}

export interface SalesOrderPayload {
  items: { cigar_id: number; sale_unit: string; quantity: number; unit_price: string; sale_quantity?: number; box_size?: number }[];
  customer_id?: number | null;
  customer_name?: string;
  payment_method_id?: number | null;
  payment_manual?: Record<string, string>;
  customer_transport_fee_cny?: string;
  transport_payer?: 'customer' | 'company';
  note?: string;
}

export interface FundAccount {
  id: number;
  name: string;
  currency: 'CNY' | 'RUB' | 'USDT' | string;
  custodian_id: number | null;
  is_active: boolean;
  original_balance?: string;
  cny_book_cost?: string;
  moving_average_cny?: string | null;
}

export interface MonthlyProfitReport {
  period_start: string;
  period_end: string;
  sales_revenue_cny: string;
  customer_transport_revenue_cny: string;
  cost_of_goods_sold_cny: string;
  transport_expense_cny: string;
  net_profit_cny: string;
  transaction_count: number;
}

export interface AccountingDashboardStats {
  cny_funds_total: string | null;
  inventory_book_cost_cny: string | null;
  accounts_receivable_cny: string | null;
  month_net_profit_cny: string | null;
}

export interface AccountingDashboard {
  requires_day1: boolean;
  day1_status: 'not_started' | 'draft' | 'completed' | string;
  stats: AccountingDashboardStats;
  accounts: (FundAccount & { original_balance: string; cny_book_cost: string })[];
  monthly_profit: MonthlyProfitReport | null;
  reconciliation: {
    pending_count: number;
    latest: { id: number; account_id: number; account_name: string; business_date: string; system_amount: string; actual_amount: string; difference: string; status: string }[];
  };
}

export interface AccountingSummary {
  as_of: string;
  fund_accounts: (FundAccount & { original_balance: string; cny_book_cost: string })[];
  accounts_receivable_cny: string;
  customer_prepayments_cny: string;
  inventory_remaining_cost_cny: string;
  purchase_in_transit_cny: string;
}

export interface Reconciliation {
  id: number;
  account_id: number;
  business_date: string;
  system_amount: string;
  actual_amount: string;
  difference: string;
  status: 'pending' | 'confirmed' | string;
  operator_id: number;
  confirmer_id: number | null;
  note: string;
  created_at: string;
  updated_at: string;
}
