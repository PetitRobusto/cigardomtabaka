export type StoreLocale = "zh" | "ru" | "en";

export type StoreProduct = {
  id: number | string;
  name: string;
  english_name: string;
  brand: string;
  brand_slug: string;
  path: string;
  description: string;
  aliases: string[];
  image_url: string | null;
  images: string[];
  image_kinds?: Record<string, string>;
  image_variants?: Array<{ url: string; thumbnail_url: string; image_type: string | null; box_size: number | null }>;
  vitola: string;
  length: number | null;
  ring_gauge: number | null;
  availability: "in_stock" | "out_of_stock" | "catalog";
  offers: Array<{ sale_unit?: "box" | "stick"; box_size: number | null; price_rub: string | null; in_stock: boolean }>;
};

export type StorePageData = {
  locale: StoreLocale;
  kind: "home" | "brand" | "product";
  view?: "catalog";
  total_products?: number;
  filters?: { q: string; brands: string[]; boxes: string[]; sort: string };
  navigation?: { brands: Array<{ name: string; english_name?: string; slug: string; path: string }>; box_sizes: number[]; has_sticks?: boolean };
  filter_options?: { brands: Array<{ name: string; english_name?: string; slug: string; path: string }>; box_sizes: number[]; has_sticks?: boolean };
  path: string;
  title: string;
  description: string;
  body: string;
  site: {
    name: string;
    address: string;
    phone: string;
    wechat: string;
    map_url: string;
    photo: string;
    points_of_sales: string;
    hours: string;
  };
  products: StoreProduct[];
  product?: StoreProduct | null;
  brands: Array<{ name: string; slug: string; path: string; count?: number }>;
  alternates: Array<{ locale: StoreLocale; path: string }>;
  browsing_alternates?: Array<{ locale: StoreLocale; path: string }>;
  breadcrumbs: Array<{ label: string; path: string }>;
  pagination: {
    page: number;
    total_pages: number;
    previous: string | null;
    next: string | null;
  };
};

export type StoreAssets = { js: string[]; css: string[] };
export type StoreRenderInput = { page: StorePageData; origin: string; assets: StoreAssets };

export type StoreRates = {
  source_updated_at: string | null;
  expires_at: string | null;
  cny_per_rub: string | null;
  usd_per_rub: string | null;
};
